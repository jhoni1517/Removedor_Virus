"""Backend da interface: FastAPI + WebSocket, reaproveitando os módulos do CelScan.

Segurança: só atende 127.0.0.1/localhost e exige o token gerado na abertura do programa
(cabeçalho X-CelScan-Token ou ?t=). Assim, uma página qualquer aberta no navegador não
consegue mandar comandos para o celular pela porta local.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from celscan import __version__, config, servicos
from celscan.acoes import backup, evidencias, navegacao, otimizacao, quarentena, recuperacao
from celscan.acoes.espelho import EspelhoErro, Espelhos, OpcoesEspelho
from celscan.acoes.espelho import localizar as localizar_scrcpy
from celscan.api import wifi
from celscan.api.tarefas import Gerenciador
from celscan.core import adb, db, log, preferencias

WEB = config.PACOTE / "web" / "dist"
HOSTS = ("127.0.0.1", "localhost", "testserver")
MARCAS: dict[str, Any] = yaml.safe_load((config.DADOS / "conexao.yaml").read_text(encoding="utf-8"))
RESGATE: dict[str, Any] = yaml.safe_load((config.DADOS / "resgate.yaml").read_text(encoding="utf-8"))


def marca_de(fabricante: str | None) -> str:
    f = (fabricante or "").lower()
    for chave, m in MARCAS["marcas"].items():
        if f in m.get("fabricantes", []):
            return chave
    return "generico"


# ---------------------------------------------------------------- modelos de entrada

class PedidoVarredura(BaseModel):
    serial: str
    modo: str = "rapido"
    sistema: bool = False


class PedidoSerial(BaseModel):
    serial: str


class PedidoLimpeza(BaseModel):
    serial: str
    categorias: list[str] = Field(default_factory=lambda: list(otimizacao.LIXO))


class PedidoRemocao(BaseModel):
    serial: str
    varredura_id: int
    pacotes: list[str] = Field(min_length=1)
    ciente_vitima: bool = False  # a pessoa leu o aviso de que remover app espião pode alertar quem instalou


class PedidoEvidencias(BaseModel):
    serial: str
    varredura_id: int
    pacotes: list[str] = Field(min_length=1)
    print_tela: bool = True


class PedidoDesfazer(BaseModel):
    serial: str
    quarentena_id: str


class PedidoConfig(BaseModel):
    chave_virustotal: str | None = None
    offline: bool | None = None
    tema: str | None = None


class PedidoEspelho(BaseModel):
    serial: str | None = None
    modo: str = "controlar"
    tela_desligada: bool = False
    acordado: bool = True
    gravar: bool = False
    compativel: bool = False  # preset para PC fraco / vídeo travando
    tamanho_max: int = 0
    fps_max: int = 0
    bitrate_mbps: int = 0
    buffer_ms: int = 0
    codec: str = ""
    sem_audio: bool = False


class PedidoAjuste(BaseModel):
    serial: str | None = None
    ajuste: str


class PedidoRecuperacao(BaseModel):
    serial: str
    categorias: list[str] = Field(default_factory=lambda: list(recuperacao.PADRAO))
    destino: str | None = None
    verificar: bool = False


class PedidoBackup(BaseModel):
    serial: str
    categorias: list[str] = Field(default_factory=lambda: list(backup.PADRAO))
    destino: str | None = None
    verificar: bool = False


class PedidoPermissoes(BaseModel):
    serial: str
    pacote: str
    acoes: list[str] = Field(default_factory=list)
    revogar: list[str] = Field(default_factory=list)


class PedidoPasta(BaseModel):
    caminho: str


class PedidoWifi(BaseModel):
    endereco: str
    codigo: str | None = None


# ---------------------------------------------------------------- aparelhos conectados

class Aparelhos:
    """Lista viva de aparelhos (adb track-devices) com marca/modelo dos que estão autorizados."""

    def __init__(self, gerenciador: Gerenciador):
        self.gerenciador = gerenciador
        self.lista: dict[str, dict[str, Any]] = {}
        self._info: dict[str, dict[str, str]] = {}
        self.parar = threading.Event()
        self.pausa = threading.Event()  # modo mouse OTG: deixa a porta USB livre para o scrcpy

    def atualizar(self, pares: list[tuple[str, str]]) -> None:
        novos = {}
        for serial, estado in pares:
            item: dict[str, Any] = {"serial": serial, "estado": estado, "wifi": ":" in serial}
            if estado == "device":
                if serial not in self._info:
                    self._info[serial] = self._ler_info(serial)
                item.update(self._info[serial])
            novos[serial] = item
        if novos != self.lista:
            self.lista = novos
            self.gerenciador.publicar({"tipo": "dispositivos", "dispositivos": list(novos.values())})

    @staticmethod
    def _ler_info(serial: str) -> dict[str, str]:
        ap = adb.Aparelho(serial)
        try:
            props = {k: ap.sh(f"getprop {k}", timeout=15) for k in
                     ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release")}
        except adb.AdbErro:
            return {}
        return {"fabricante": props["ro.product.manufacturer"], "modelo": props["ro.product.model"],
                "android": props["ro.build.version.release"], "marca": marca_de(props["ro.product.manufacturer"])}

    def iniciar(self) -> None:
        def rodar() -> None:
            try:
                self.atualizar(adb.dispositivos())
            except adb.AdbErro:
                pass
            adb.acompanhar(self.atualizar, self.parar, pausa=self.pausa)

        threading.Thread(target=rodar, name="celscan-aparelhos", daemon=True).start()

    def reiniciar(self) -> list[dict[str, Any]]:
        """Reinicia o servidor adb (resolve briga com outro adb) e relista os aparelhos agora."""
        self.parar.set()
        try:
            adb.run(["kill-server"], timeout=15)
        except adb.AdbErro:
            pass
        self._info.clear()
        self.parar = threading.Event()
        try:
            self.atualizar(adb.dispositivos())
        except adb.AdbErro:
            pass
        self.iniciar()
        return list(self.lista.values())

    def pronto(self, serial: str) -> adb.Aparelho:
        item = self.lista.get(serial)
        if not item or item["estado"] != "device":
            # a lista pode estar atrasada: confere direto
            try:
                prontos = [s for s, e in adb.dispositivos() if e == "device"]
            except adb.AdbErro:
                prontos = []
            if serial not in prontos:
                raise HTTPException(409, "Aparelho não conectado ou não autorizado. Reconecte o cabo e aceite a "
                                         "depuração USB no celular.")
        return adb.Aparelho(serial)


# ---------------------------------------------------------------- aplicativo

def criar_app(token: str | None = None, observar: bool = True) -> FastAPI:
    token = token or secrets.token_urlsafe(24)
    tarefas = Gerenciador()
    aparelhos = Aparelhos(tarefas)
    espelhos = Espelhos()
    erros = (adb.AdbErro, servicos.ModoIndisponivel, ValueError)

    @asynccontextmanager
    async def ciclo(_app: FastAPI):
        log.configurar()
        preferencias.aplicar()
        if observar and adb.localizar():
            aparelhos.iniciar()
        yield
        aparelhos.parar.set()
        espelhos.parar_todas()

    app = FastAPI(title="CelScan", version=__version__, lifespan=ciclo, docs_url=None, redoc_url=None)
    app.state.token, app.state.tarefas, app.state.aparelhos = token, tarefas, aparelhos

    @app.middleware("http")
    async def proteger(request: Request, chamar):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in HOSTS:
            return JSONResponse({"detail": "host não permitido"}, status_code=403)
        if request.url.path.startswith("/api/"):
            recebido = request.headers.get("x-celscan-token") or request.query_params.get("t")
            if not recebido or not secrets.compare_digest(recebido, token):
                return JSONResponse({"detail": "token inválido"}, status_code=401)
        return await chamar(request)

    def nova_tarefa(tipo: str, serial: str | None, funcao) -> dict[str, Any]:
        if serial and (ocupada := tarefas.ocupado(serial)):
            raise HTTPException(409, f"Já existe uma operação em andamento neste aparelho ({ocupada.tipo}).")
        return tarefas.criar(tipo, serial, funcao, erros).publico()

    # ---- estado geral
    @app.get("/api/estado")
    def estado() -> dict[str, Any]:
        return {"versao": __version__, "adb": adb.localizar() is not None, "offline": config.OFFLINE,
                "vt": preferencias.chave_virustotal() is not None, "modos": servicos.MODOS,
                "dispositivos": list(aparelhos.lista.values()),
                "tarefas": [t.publico() for t in tarefas.listar() if t.estado == "executando"]}

    @app.post("/api/adb/reconectar")
    def reconectar() -> dict[str, Any]:
        if not adb.localizar():
            raise HTTPException(503, "ADB não encontrado. Use o botão para baixar.")
        return {"dispositivos": aparelhos.reiniciar()}

    @app.post("/api/adb/instalar")
    def instalar_adb() -> dict[str, Any]:
        def rodar(progresso, _cancelar):
            progresso({"etapa": "adb", "descricao": "Baixando o ADB oficial do Google", "atual": None,
                       "total": None, "detalhe": "", "estimativa_s": 20})
            caminho = adb.instalar_platform_tools()
            aparelhos.iniciar()
            return {"adb": caminho}
        return nova_tarefa("instalar_adb", None, rodar)

    @app.get("/api/ajuda/conexao")
    def ajuda_conexao() -> dict[str, Any]:
        return MARCAS

    @app.get("/api/conexao/driver")
    def diagnostico_driver() -> dict[str, Any]:
        """No Windows, aponta celular com driver USB com problema (causa nº 1 de 'não aparece')."""
        from celscan.core import drivers
        return drivers.diagnosticar()

    # ---- varreduras
    @app.post("/api/varreduras")
    def varrer(p: PedidoVarredura) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        opcoes = servicos.OpcoesVarredura(modo=p.modo, sistema=p.sistema)
        if p.modo == "profundo":
            raise HTTPException(422, "O modo Profundo (AndroidQF + MVT) chega na Etapa B. Use o Completo.")

        def rodar(progresso, cancelar):
            return servicos.executar_varredura(ap, opcoes, progresso, cancelar).como_dict()
        return nova_tarefa("varredura", p.serial, rodar)

    @app.get("/api/varreduras")
    def listar_varreduras(serial: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
        return [dict(v) for v in db.varreduras(db.conectar(), serial, limite)]

    @app.get("/api/varreduras/{vid}")
    def obter_varredura(vid: int) -> dict[str, Any]:
        con = db.conectar()
        retrato = db.retrato(con, vid)
        if retrato is None:
            raise HTTPException(404, "Varredura não encontrada")
        meta = con.execute("SELECT id, serial, data, modo, nota, veredito, duracao_s FROM varreduras WHERE id=?",
                           (vid,)).fetchone()
        return {**dict(meta), **retrato}

    # ---- ações
    @app.post("/api/remover")
    def remover(p: PedidoRemocao) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        retrato = db.retrato(db.conectar(), p.varredura_id)
        if retrato is None:
            raise HTTPException(404, "Varredura não encontrada")
        por_pacote = {r["pacote"]: r for r in retrato["apps"]}
        faltando = [x for x in p.pacotes if x not in por_pacote]
        if faltando:
            raise HTTPException(422, f"Apps fora desta varredura: {', '.join(faltando)}")
        alvos = [dict(por_pacote[x]) for x in p.pacotes]
        espioes = [a["pacote"] for a in alvos if evidencias.eh_vigilancia(a)]
        if espioes and not p.ciente_vitima:
            raise HTTPException(409, "MODO_VITIMA: remover app espião pode alertar quem instalou. "
                                     "Mostre o aviso e confirme (ciente_vitima) antes. Apps: " + ", ".join(espioes))

        def rodar(progresso, cancelar):
            return servicos.remover_apps(ap, alvos, progresso, cancelar)
        return nova_tarefa("remocao", p.serial, rodar)

    # ---- proteção à vítima de stalkerware
    @app.get("/api/apoio")
    def apoio() -> dict[str, Any]:
        return evidencias.APOIO

    @app.post("/api/evidencias")
    def documentar(p: PedidoEvidencias) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        retrato = db.retrato(db.conectar(), p.varredura_id)
        if retrato is None:
            raise HTTPException(404, "Varredura não encontrada")
        por_pacote = {r["pacote"]: r for r in retrato["apps"]}
        achados = [dict(por_pacote[x]) for x in p.pacotes if x in por_pacote]
        if not achados:
            raise HTTPException(422, "Nenhum desses apps está nesta varredura")
        destino = destino_backup(p.serial, None)
        info = {k: v for k, v in aparelhos.lista.get(p.serial, {}).items() if isinstance(v, str)}

        def rodar(progresso, cancelar):
            progresso({"etapa": "evidencias", "descricao": "Guardando as provas (sem mexer no celular)",
                       "detalhe": "", "atual": None, "total": None, "estimativa_s": 15})
            return evidencias.documentar(ap, achados, destino, info, p.print_tela)
        return nova_tarefa("evidencias", p.serial, rodar)

    @app.get("/api/permissoes/acoes")
    def permissoes_acoes() -> dict[str, Any]:
        from celscan.acoes import permissoes
        return {"acoes": permissoes.ACOES, "permissoes": permissoes.PERMISSOES}

    @app.post("/api/permissoes")
    def aplicar_permissoes(p: PedidoPermissoes) -> dict[str, Any]:
        from celscan.acoes import permissoes

        ap = aparelhos.pronto(p.serial)
        if not p.acoes and not p.revogar:
            raise HTTPException(422, "Escolha ao menos uma ação")

        def rodar(progresso, _cancelar):
            progresso({"etapa": "permissoes", "descricao": "Ajustando permissões", "detalhe": p.pacote,
                       "atual": None, "total": None, "estimativa_s": 5})
            r = permissoes.aplicar(ap, p.pacote, p.acoes, p.revogar)
            db.registrar_acao(db.conectar(), p.serial, "permissoes", p.pacote, ", ".join(r["feitas"]),
                              r["quarentena_id"])
            return r
        return nova_tarefa("permissoes", p.serial, rodar)

    @app.post("/api/desfazer")
    def desfazer(p: PedidoDesfazer) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, _cancelar):
            progresso({"etapa": "desfazer", "descricao": "Desfazendo", "detalhe": p.quarentena_id, "atual": None,
                       "total": None, "estimativa_s": 15})
            return servicos.desfazer(ap, p.quarentena_id)
        return nova_tarefa("desfazer", p.serial, rodar)

    @app.get("/api/varreduras/{vid}/laudo.pdf")
    def laudo_pdf(vid: int, versao: str = "cliente", loja: str | None = None) -> Response:
        from celscan.relatorio import pdf

        con = db.conectar()
        meta, retrato = db.meta_varredura(con, vid), db.retrato(con, vid)
        if meta is None or retrato is None:
            raise HTTPException(404, "Varredura não encontrada")
        try:
            conteudo, h = pdf.gerar_pdf(meta, retrato, versao, loja, db.acoes_da_varredura(con, vid))
        except ValueError as e:
            raise HTTPException(422, str(e))
        db.registrar_laudo(con, vid, h)
        nome = f"laudo_celscan_{vid}_{versao}.pdf"
        return Response(conteudo, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{nome}"'})

    @app.get("/api/laudos/verificar")
    def verificar_laudo(codigo: str) -> dict[str, Any]:
        achado = db.verificar_laudo(db.conectar(), codigo)
        if not achado:
            raise HTTPException(404, "Código não encontrado neste computador. O laudo pode ser falso ou ter sido "
                                     "emitido em outro computador.")
        return achado

    @app.get("/api/quarentena")
    def listar_quarentena() -> list[dict[str, Any]]:
        return quarentena.listar()

    @app.get("/api/acoes")
    def listar_acoes(serial: str | None = None) -> list[dict[str, Any]]:
        return [dict(a) for a in db.acoes(db.conectar(), serial)]

    # ---- tarefas
    @app.get("/api/tarefas/{ident}")
    def obter_tarefa(ident: str) -> dict[str, Any]:
        t = tarefas.obter(ident)
        if not t:
            raise HTTPException(404, "Tarefa não encontrada")
        return t.publico()

    @app.post("/api/tarefas/{ident}/cancelar")
    def cancelar_tarefa(ident: str) -> dict[str, bool]:
        return {"cancelando": tarefas.cancelar(ident)}

    # ---- configurações
    @app.get("/api/config")
    def ler_config() -> dict[str, Any]:
        c = preferencias.ler()
        chave = preferencias.chave_virustotal()
        return {"chave_virustotal": f"…{chave[-4:]}" if chave else None, "offline": config.OFFLINE,
                "tema": c.get("tema", "sistema"), "pasta_dados": str(config.DIR)}

    @app.put("/api/config")
    def salvar_config(p: PedidoConfig) -> dict[str, Any]:
        preferencias.salvar(**p.model_dump())
        return ler_config()

    # ---- Wi-Fi
    @app.post("/api/wifi/qr")
    def wifi_qr() -> dict[str, Any]:
        convite = wifi.novo_convite()
        tarefa = nova_tarefa("wifi", None, lambda progresso, cancelar: wifi.esperar_pareamento(
            convite, progresso, cancelar))
        return {**convite.publico(), "tarefa": tarefa}

    @app.post("/api/wifi/parear")
    def wifi_parear(p: PedidoWifi) -> dict[str, str]:
        if not p.codigo:
            raise HTTPException(422, "Informe o código de 6 dígitos")
        return {"resposta": adb.parear(p.endereco, p.codigo)}

    @app.post("/api/wifi/conectar")
    def wifi_conectar(p: PedidoWifi) -> dict[str, str]:
        return {"resposta": adb.conectar(p.endereco)}

    # ---- proteção Pix: certificados oficiais dos apps de banco
    @app.post("/api/certificados/registrar")
    def registrar_certificados(serial: str) -> dict[str, Any]:
        from celscan.analise import certificados

        alvo = serial
        ap = aparelhos.pronto(alvo)

        def rodar(progresso, _cancelar):
            progresso({"etapa": "certificados", "descricao": "Lendo certificados dos apps de banco", "detalhe": "",
                       "atual": None, "total": None, "estimativa_s": 10})
            return certificados.registrar_do_aparelho(ap)
        return nova_tarefa("certificados", alvo, rodar)

    # ---- tela quebrada: espelhar e copiar dados
    @app.get("/api/resgate")
    def guia_resgate() -> dict[str, Any]:
        return RESGATE

    @app.get("/api/espelho")
    def estado_espelho() -> dict[str, Any]:
        return {"disponivel": localizar_scrcpy() is not None, "ativas": espelhos.ativas()}

    @app.post("/api/espelho")
    def abrir_espelho(p: PedidoEspelho) -> dict[str, Any]:
        if p.modo != "otg":
            if not p.serial:
                raise HTTPException(422, "Escolha o aparelho")
            aparelhos.pronto(p.serial)
        gravacao = None
        if p.gravar and p.modo != "otg":
            nome = backup.nome_seguro(f"tela_{p.serial}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
            gravacao = str(backup.pasta_padrao() / "Gravações de tela" / nome)
        if p.compativel:
            opcoes = OpcoesEspelho.compativel(p.modo)
            opcoes.tela_desligada, opcoes.acordado, opcoes.gravar = p.tela_desligada, p.acordado, gravacao
        else:
            opcoes = OpcoesEspelho(
                modo=p.modo, tela_desligada=p.tela_desligada, acordado=p.acordado, gravar=gravacao,
                tamanho_max=p.tamanho_max, fps_max=p.fps_max, bitrate_mbps=p.bitrate_mbps,
                buffer_ms=p.buffer_ms, codec=p.codec, sem_audio=p.sem_audio,
            )
        if p.modo == "otg":
            aparelhos.pausa.set()  # o adb precisa soltar o celular para o modo mouse funcionar
            try:
                adb.run(["kill-server"], timeout=15)
            except adb.AdbErro:
                pass
        try:
            sessao = espelhos.abrir(p.serial, opcoes)
        except (EspelhoErro, ValueError) as e:
            aparelhos.pausa.clear()
            raise HTTPException(422, str(e))
        erro = espelhos.erro_inicial(sessao)
        if p.modo == "otg":
            def retomar() -> None:
                sessao.processo.wait()
                aparelhos.pausa.clear()
            threading.Thread(target=retomar, daemon=True).start()
        if erro:
            raise HTTPException(422, f"O espelhamento não abriu: {erro}")
        return {"ok": True, "modo": p.modo, "gravacao": gravacao}

    @app.post("/api/espelho/parar")
    def parar_espelho(p: PedidoEspelho) -> dict[str, bool]:
        return {"parado": espelhos.parar(p.serial if p.modo != "otg" else None)}

    @app.get("/api/ajustes")
    def listar_ajustes() -> dict[str, str]:
        return {k: v[0] for k, v in navegacao.AJUSTES.items()}

    @app.post("/api/ajustes/abrir")
    def abrir_ajuste(p: PedidoAjuste) -> dict[str, str]:
        ap = aparelhos.pronto(p.serial)
        try:
            return {"aberto": navegacao.abrir_ajuste(ap, p.ajuste)}
        except ValueError as e:
            raise HTTPException(422, str(e))

    # ---- iPhone (leitura por USB via libimobiledevice)
    @app.get("/api/ios/estado")
    def ios_estado() -> dict[str, Any]:
        from celscan.ios import mvt as ios
        if not ios.ferramentas_ok():
            return {"disponivel": False, "aparelhos": [],
                    "aviso": "Para ver iPhones, instale o libimobiledevice (idevice_id, ideviceinfo). "
                             "No Windows ele vem com o iTunes/Apple Devices."}
        try:
            udids = ios.aparelhos()
        except Exception as e:
            return {"disponivel": True, "aparelhos": [], "aviso": str(e)}
        aparelhos_ios = []
        for u in udids:
            try:
                aparelhos_ios.append({"udid": u, **ios.info(u)})
            except Exception as e:
                aparelhos_ios.append({"udid": u, "erro": str(e)})
        return {"disponivel": True, "aparelhos": aparelhos_ios}

    # ---- diagnóstico e limpeza segura
    @app.post("/api/diagnostico")
    def diagnostico(p: PedidoSerial) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, cancelar):
            progresso({"etapa": "diagnostico", "descricao": "Lendo bateria, armazenamento, memória e IMEI",
                       "detalhe": "", "atual": None, "total": None, "estimativa_s": 30})
            return otimizacao.diagnostico(ap)
        return nova_tarefa("diagnostico", p.serial, rodar)

    @app.post("/api/limpeza/cache")
    def limpar_cache(p: PedidoSerial) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, cancelar):
            progresso({"etapa": "limpeza", "descricao": "Limpando o cache dos apps", "detalhe": "",
                       "atual": None, "total": None, "estimativa_s": 40})
            return {"liberado_mb": otimizacao.limpar_cache(ap)}
        return nova_tarefa("limpeza_cache", p.serial, rodar)

    @app.post("/api/limpeza/lixo")
    def medir_lixo(p: PedidoSerial) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        itens = otimizacao.medir_lixo(ap)
        return {"itens": itens, "total_mb": sum(i["kb"] for i in itens) / 1024}

    @app.post("/api/limpeza/lixo/apagar")
    def apagar_lixo(p: PedidoLimpeza) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        try:
            return {"liberado_mb": otimizacao.limpar_lixo(ap, p.categorias)}
        except ValueError as e:
            raise HTTPException(422, str(e))

    # ---- recuperação de sobras (lixeira, miniaturas, mídia deixada nos apps) — sem root
    @app.get("/api/recuperacao/categorias")
    def categorias_recuperacao() -> dict[str, Any]:
        cats = {c: recuperacao.nome_categoria(c) for c in (*recuperacao.FONTES, *recuperacao.PASTAS_APP)}
        return {"categorias": cats, "padrao": list(recuperacao.PADRAO),
                "aviso": "Sem root não há recuperação de arquivos realmente apagados nem de mensagens do "
                         "WhatsApp. O CelScan resgata o que ainda está no aparelho: lixeira da galeria, "
                         "miniaturas e mídia que sobrou dentro dos apps."}

    @app.post("/api/recuperacao/procurar")
    def procurar_recuperacao(p: PedidoRecuperacao) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, cancelar):
            progresso({"etapa": "listar", "descricao": "Procurando o que dá para recuperar", "detalhe": "",
                       "atual": None, "total": None, "estimativa_s": 25})
            arquivos = recuperacao.procurar(ap, p.categorias)
            return {"categorias": recuperacao.resumo(arquivos), "total_arquivos": len(arquivos),
                    "total_bytes": sum(a.tamanho for a in arquivos)}
        return nova_tarefa("recuperacao_procurar", p.serial, rodar)

    @app.post("/api/recuperacao/recuperar")
    def recuperar(p: PedidoRecuperacao) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        raiz = destino_backup(p.serial, p.destino)

        def rodar(progresso, cancelar):
            from dataclasses import asdict

            progresso({"etapa": "listar", "descricao": "Procurando o que dá para recuperar", "detalhe": "",
                       "atual": None, "total": None, "estimativa_s": 25})
            arquivos = recuperacao.procurar(ap, p.categorias)
            raiz.mkdir(parents=True, exist_ok=True)
            info = {k: v for k, v in aparelhos.lista.get(p.serial, {}).items() if isinstance(v, str)}
            return asdict(backup.copiar(ap, arquivos, raiz, progresso, cancelar, p.verificar, info,
                                        destino_de=recuperacao.destino_recuperado))
        return nova_tarefa("recuperacao", p.serial, rodar)

    def destino_backup(serial: str, destino: str | None) -> Path:
        if destino:
            return Path(destino).expanduser()
        d = aparelhos.lista.get(serial, {})
        nome = backup.nome_seguro(f"{d.get('fabricante', '')} {d.get('modelo', '')} ({serial})".strip())
        return backup.pasta_padrao() / nome  # mesmo nome sempre: rodar de novo continua de onde parou

    @app.get("/api/backup/categorias")
    def categorias_backup(serial: str | None = None) -> dict[str, Any]:
        return {"categorias": {k: v[0] for k, v in backup.CATEGORIAS.items()}, "padrao": list(backup.PADRAO),
                "destino": str(destino_backup(serial, None)) if serial else str(backup.pasta_padrao())}

    @app.post("/api/backup/listar")
    def listar_backup(p: PedidoBackup) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, cancelar):
            progresso({"etapa": "listar", "descricao": "Procurando arquivos no celular", "detalhe": "", "atual": None,
                       "total": None, "estimativa_s": 20})
            arquivos = backup.listar(ap, p.categorias)
            return {"categorias": backup.resumo_listagem(arquivos), "total_arquivos": len(arquivos),
                    "total_bytes": sum(a.tamanho for a in arquivos),
                    "destino": str(destino_backup(p.serial, p.destino))}
        return nova_tarefa("backup_listar", p.serial, rodar)

    @app.post("/api/backup/copiar")
    def copiar_backup(p: PedidoBackup) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)
        raiz = destino_backup(p.serial, p.destino)

        def rodar(progresso, cancelar):
            from dataclasses import asdict

            progresso({"etapa": "listar", "descricao": "Procurando arquivos no celular", "detalhe": "", "atual": None,
                       "total": None, "estimativa_s": 20})
            arquivos = backup.listar(ap, p.categorias)
            raiz.mkdir(parents=True, exist_ok=True)
            (raiz / "apps_instalados.txt").write_text(backup.lista_de_apps(ap), encoding="utf-8")
            info = {k: v for k, v in aparelhos.lista.get(p.serial, {}).items() if isinstance(v, str)}
            return asdict(backup.copiar(ap, arquivos, raiz, progresso, cancelar, p.verificar, info))
        return nova_tarefa("backup", p.serial, rodar)

    @app.post("/api/abrir-pasta")
    def abrir_pasta(p: PedidoPasta) -> dict[str, bool]:
        alvo = Path(p.caminho).expanduser().resolve()
        permitidas = [backup.pasta_padrao().resolve(), config.DIR.resolve()]
        if not any(alvo == r or r in alvo.parents for r in permitidas):
            raise HTTPException(403, "Só abro pastas do CelScan")
        alvo.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(alvo)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(alvo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"aberta": True}

    # ---- tempo real
    @app.websocket("/api/ws")
    async def tempo_real(ws: WebSocket) -> None:
        recebido = ws.query_params.get("t") or ""
        if not secrets.compare_digest(recebido, token):
            await ws.close(code=4401)
            return
        await ws.accept()
        fila: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def ouvinte(msg: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(fila.put_nowait, msg)

        tarefas.ouvir(ouvinte)
        try:
            await ws.send_json({"tipo": "estado", **estado()})
            while True:
                await ws.send_json(await fila.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            tarefas.parar_de_ouvir(ouvinte)

    # ---- interface (arquivos do React já compilados)
    if (WEB / "index.html").exists():
        # Injeta o token direto na página, para não depender de query-string nem sessionStorage
        # (em algumas versões do WebView2 do Windows o ?t= não chega ao JavaScript).
        @app.get("/", response_class=HTMLResponse)
        def raiz() -> str:
            html = (WEB / "index.html").read_text(encoding="utf-8")
            return html.replace("<head>", f'<head><script>window.__CELSCAN_TOKEN__="{token}";</script>', 1)

        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def sem_interface() -> str:
            return ("<h1>CelScan</h1><p>A interface ainda não foi compilada. Rode <code>npm install && npm run "
                    "build</code> em <code>celscan/web</code>.</p>")

    @app.exception_handler(adb.AdbAusente)
    async def sem_adb(_r: Request, e: Exception) -> Response:
        return JSONResponse({"detail": "ADB não encontrado. Use o botão para baixar."}, status_code=503)

    return app


def pasta_web() -> Path:
    return WEB

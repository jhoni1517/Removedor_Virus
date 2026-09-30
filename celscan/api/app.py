"""Backend da interface: FastAPI + WebSocket, reaproveitando os módulos do CelScan.

Segurança: só atende 127.0.0.1/localhost e exige o token gerado na abertura do programa
(cabeçalho X-CelScan-Token ou ?t=). Assim, uma página qualquer aberta no navegador não
consegue mandar comandos para o celular pela porta local.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from celscan import __version__, config, servicos
from celscan.acoes import quarentena
from celscan.api import wifi
from celscan.api.tarefas import Gerenciador
from celscan.core import adb, db, log, preferencias

WEB = config.PACOTE / "web" / "dist"
HOSTS = ("127.0.0.1", "localhost", "testserver")
MARCAS: dict[str, Any] = yaml.safe_load((config.DADOS / "conexao.yaml").read_text(encoding="utf-8"))


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


class PedidoRemocao(BaseModel):
    serial: str
    varredura_id: int
    pacotes: list[str] = Field(min_length=1)


class PedidoDesfazer(BaseModel):
    serial: str
    quarentena_id: str


class PedidoConfig(BaseModel):
    chave_virustotal: str | None = None
    offline: bool | None = None
    tema: str | None = None


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
            adb.acompanhar(self.atualizar, self.parar)

        threading.Thread(target=rodar, name="celscan-aparelhos", daemon=True).start()

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
    erros = (adb.AdbErro, servicos.ModoIndisponivel, ValueError)

    @asynccontextmanager
    async def ciclo(_app: FastAPI):
        log.configurar()
        preferencias.aplicar()
        if observar and adb.localizar():
            aparelhos.iniciar()
        yield
        aparelhos.parar.set()

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

        def rodar(progresso, cancelar):
            return servicos.remover_apps(ap, alvos, progresso, cancelar)
        return nova_tarefa("remocao", p.serial, rodar)

    @app.post("/api/desfazer")
    def desfazer(p: PedidoDesfazer) -> dict[str, Any]:
        ap = aparelhos.pronto(p.serial)

        def rodar(progresso, _cancelar):
            progresso({"etapa": "desfazer", "descricao": "Desfazendo", "detalhe": p.quarentena_id, "atual": None,
                       "total": None, "estimativa_s": 15})
            return servicos.desfazer(ap, p.quarentena_id)
        return nova_tarefa("desfazer", p.serial, rodar)

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

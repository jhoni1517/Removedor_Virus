from celscan.acoes import otimizacao, quarentena


class AparelhoFalso:
    """Guarda settings em memória e registra os comandos."""

    serial = "TESTE1"

    def __init__(self):
        self.settings = {("global", "window_animation_scale"): "1.0"}
        self.comandos = []

    def sh(self, cmd, timeout=120, erro=False):
        self.comandos.append(cmd)
        partes = cmd.split()
        if partes[:2] == ["settings", "get"]:
            return self.settings.get((partes[2], partes[3]), "null")
        if partes[:2] == ["settings", "put"]:
            self.settings[(partes[2], partes[3])] = partes[4].strip("'")
        if partes[:2] == ["settings", "delete"]:
            self.settings.pop((partes[2], partes[3]), None)
        return ""

    def adb(self, *args, **kw):
        return ""


def test_animacoes_registra_e_desfaz():
    ap = AparelhoFalso()
    ident = otimizacao.animacoes(ap, 0.5)
    assert ap.settings[("global", "window_animation_scale")] == "0.5"
    assert ap.settings[("global", "animator_duration_scale")] == "0.5"
    ok, msg = quarentena.restaurar(ap, ident)
    assert ok, msg
    assert ap.settings[("global", "window_animation_scale")] == "1.0"
    assert ("global", "animator_duration_scale") not in ap.settings  # antes não existia
    assert any(m["id"] == ident and m.get("restaurado") for m in quarentena.listar())


def test_restaurar_id_inexistente():
    assert quarentena.restaurar(AparelhoFalso(), "nao_existe") == (False, "ID não encontrado na quarentena")

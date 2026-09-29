# Fixtures

- `sintetico/`: saídas **escritas à mão** no formato documentado do Android (não vieram de um
  aparelho real). Servem para testar a lógica sem celular.
- `sintetico/variantes/`: trechos no formato de outras versões/fabricantes, reconstruídos a partir
  do código-fonte do AOSP e de relatos públicos. **Precisam ser confirmados com aparelho real.**
- `<fabricante>_<modelo>_android<versão>/`: saídas **reais**, gravadas com
  `python celscan.py fixtures` num celular conectado (seriais e IMEI anonimizados).

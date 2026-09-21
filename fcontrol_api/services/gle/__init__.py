"""Serviços do domínio GLE.

- calculo: regras puras de dias, fatores, sobreposição e arredondamento.
- apuracao: cálculo da missão com os soldos vigentes.
- localidades: validação e atualização do cadastro global.
- missoes: substituição de trechos e militares, preservando o posto salvo.
- leitura: montagem dos detalhes e resumos exibidos pela API.
- pesquisa: agrupamento das etapas que tocaram localidades especiais.
- auditoria: snapshots determinísticos para o registro de alterações.

Os routers mantêm RBAC, consultas de escopo, resposta HTTP e commit.
Serviços podem executar flush, mas não encerram a transação.
Importe cada operação do submódulo responsável.
"""

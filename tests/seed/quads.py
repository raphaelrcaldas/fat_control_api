"""Seed data for Quads.

Dados baseados no ambiente de produção (Supabase).
Representa a estrutura de quadrinhos operacionais do 1GT.
"""

from fcontrol_api.models.public.quads import QuadsFunc, QuadsGroup, QuadsType

# Grupos de quadrinhos (categorias principais)
QUADS_GROUPS = [
    QuadsGroup(short='sobr', long='sobreaviso', uae='11gt'),
    QuadsGroup(short='nasc', long='nacional', uae='11gt'),
    QuadsGroup(short='local', long='local', uae='11gt'),
    QuadsGroup(short='desloc', long='deslocamento', uae='11gt'),
    QuadsGroup(short='inter', long='internacional', uae='11gt'),
]

# Tipos de quadrinhos (vinculados aos grupos)
# IDs seguem a ordem de inserção: 1, 2, 3...
QUADS_TYPES = [
    # Grupo 1 - Sobreaviso (group_id=1)
    QuadsType(group_id=1, short='pto', long='preto'),  # type_id=1
    QuadsType(group_id=1, short='vmo', long='vermelho'),  # type_id=2
    QuadsType(group_id=1, short='roxo', long='roxo'),  # type_id=3
    # Grupo 2 - Nacional (group_id=2)
    QuadsType(group_id=2, short='bp', long='bate-pronto'),  # type_id=4
    QuadsType(group_id=2, short='nasc', long='nacional'),  # type_id=5
    QuadsType(group_id=2, short='calha', long='calha-norte'),  # type_id=6
    # Grupo 3 - Local (group_id=3)
    QuadsType(group_id=3, short='local', long='local'),  # type_id=7
    QuadsType(group_id=3, short='cds', long='cds'),  # type_id=8
    QuadsType(group_id=3, short='heavy', long='heavy'),  # type_id=9
    # Grupo 4 - Deslocamento (group_id=4)
    QuadsType(group_id=4, short='revo', long='revo'),  # type_id=10
    QuadsType(group_id=4, short='sar', long='sar'),  # type_id=11
    QuadsType(group_id=4, short='taet', long='taet'),  # type_id=12
    # Grupo 5 - Internacional (group_id=5)
    QuadsType(group_id=5, short='embraer', long='embraer'),  # type_id=13
    QuadsType(group_id=5, short='antartica', long='antartica'),  # type_id=14
]

# Funções associadas aos tipos de quadrinhos
# Funções possíveis: pil, mc, lm, tf, os, oe
QUADS_FUNCS = [
    # Sobreaviso - Preto (type_id=1) - todas as funções
    QuadsFunc(type_id=1, func='pil'),
    QuadsFunc(type_id=1, func='mc'),
    QuadsFunc(type_id=1, func='lm'),
    QuadsFunc(type_id=1, func='tf'),
    QuadsFunc(type_id=1, func='os'),
    QuadsFunc(type_id=1, func='oe'),
    # Sobreaviso - Vermelho (type_id=2) - todas as funções
    QuadsFunc(type_id=2, func='pil'),
    QuadsFunc(type_id=2, func='mc'),
    QuadsFunc(type_id=2, func='lm'),
    QuadsFunc(type_id=2, func='tf'),
    QuadsFunc(type_id=2, func='os'),
    QuadsFunc(type_id=2, func='oe'),
    # Sobreaviso - Roxo (type_id=3) - todas as funções
    QuadsFunc(type_id=3, func='pil'),
    QuadsFunc(type_id=3, func='mc'),
    QuadsFunc(type_id=3, func='lm'),
    QuadsFunc(type_id=3, func='tf'),
    QuadsFunc(type_id=3, func='os'),
    QuadsFunc(type_id=3, func='oe'),
    # Nacional - Bate-pronto (type_id=4) - funções limitadas
    QuadsFunc(type_id=4, func='pil'),
    QuadsFunc(type_id=4, func='mc'),
    QuadsFunc(type_id=4, func='lm'),
    QuadsFunc(type_id=4, func='tf'),
    QuadsFunc(type_id=4, func='oe'),
    # Nacional - Nacional (type_id=5)
    QuadsFunc(type_id=5, func='pil'),
    QuadsFunc(type_id=5, func='mc'),
    QuadsFunc(type_id=5, func='lm'),
    QuadsFunc(type_id=5, func='tf'),
    QuadsFunc(type_id=5, func='oe'),
    # Local - Local (type_id=7)
    QuadsFunc(type_id=7, func='mc'),
    QuadsFunc(type_id=7, func='lm'),
    QuadsFunc(type_id=7, func='tf'),
    QuadsFunc(type_id=7, func='os'),
    QuadsFunc(type_id=7, func='oe'),
]

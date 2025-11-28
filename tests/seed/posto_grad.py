from fcontrol_api.models.public.posto_grad import PostoGrad

POSTOS_GRAD_DATA = [
    (1, 'tb', 'ten brig', 'tenente-brigadeiro', 'of_gen'),
    (2, 'mb', 'maj brig', 'major-brigadeiro', 'of_gen'),
    (3, 'br', 'brig', 'brigadeiro', 'of_gen'),
    (4, 'cl', 'cel', 'coronel', 'of_sup'),
    (5, 'tc', 'ten cel', 'tenente-coronel', 'of_sup'),
    (6, 'mj', 'maj', 'major', 'of_sup'),
    (7, 'cp', 'cap', 'capitão', 'of_int'),
    (8, '1t', '1º ten', 'primeiro tenente', 'of_sub'),
    (9, '2t', '2º ten', 'segundo tenente', 'of_sub'),
    (10, 'as', 'asp', 'aspirante', 'of_sub'),
    (11, 'so', 'sub of', 'suboficial', 'grad'),
    (12, '1s', '1º sgt', 'primeiro sargento', 'grad'),
    (13, '2s', '2º sgt', 'segundo sargento', 'grad'),
    (14, '3s', '3º sgt', 'terceiro sargento', 'grad'),
    (15, 'cb', 'cabo', 'cabo', 'praça'),
    (16, 's1', 's1', 'soldado primeira classe', 'praça'),
    (17, 's2', 's2', 'soldado segunda classe', 'praça'),
]

POSTOS_GRAD = [
    PostoGrad(ant=ant, short=short, mid=mid, long=long_, circulo=circulo)
    for ant, short, mid, long_, circulo in POSTOS_GRAD_DATA
]

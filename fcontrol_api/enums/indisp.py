from enum import Enum


class IndispEnum(str, Enum):
    servico = 'svc'
    saude = 'sde'
    repr = 'rep'
    ferias = 'fer'
    licenca = 'lic'
    missao = 'mis'
    ordem_mis = 'odm'
    pessoal = 'pes'

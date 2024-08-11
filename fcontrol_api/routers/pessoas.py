from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Pessoa
from fcontrol_api.schemas.pessoas import ListPessoa, PessoaSchema

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/pessoas', tags=['pessoas'])


@router.post('/', status_code=HTTPStatus.CREATED)
def create_pessoa(pessoa: PessoaSchema, session: Session):
    if not pessoa.saram:
        db_pessoa_saram = session.scalar(select(Pessoa).where(Pessoa.saram))

        if db_pessoa_saram:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='SARAM já registrado',
            )

    if not pessoa.id_fab:
        db_pessoa_id = session.scalar(select(Pessoa).where(Pessoa.id_fab))

        if db_pessoa_id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='ID FAB já registrado',
            )

    db_pessoa = Pessoa(
        pg=pessoa.pg,
        nome_guerra=pessoa.nome_guerra,
        nome_completo=pessoa.nome_completo,
        ult_promo=pessoa.ult_promo,
        id_fab=pessoa.id_fab,
        saram=pessoa.saram,
        cpf=pessoa.cpf,
        nasc=pessoa.nasc,
        celular=pessoa.celular,
        email_pess=pessoa.email_pess,
        email_fab=pessoa.email_fab,
        unidade=pessoa.unidade,
    )

    session.add(db_pessoa)
    session.commit()
    session.refresh(db_pessoa)

    return {'detail': 'Adicionado com sucesso'}


@router.get('/', response_model=ListPessoa)
def read_pessoas(session: Session):
    pessoas = session.scalars(select(Pessoa)).all()
    return {'data': pessoas}


@router.get('/{pess_id}')  # , response_model = PessoaSchema)
def get_pessoa(pess_id, session: Session):
    query = select(Pessoa).where(Pessoa.id == pess_id)
    db_pess: Pessoa = session.scalar(query)

    if not db_pess:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    return {'data': db_pess}


@router.put('/{pess_id}')
def update_pessoa(pess_id: int, pessoa: PessoaSchema, session: Session):
    query = select(Pessoa).where(Pessoa.id == pess_id)

    db_pess: Pessoa = session.scalar(query)

    if not db_pess:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    for key, value in pessoa.model_dump(exclude_unset=True).items():
        setattr(db_pess, key, value)

    # db_pess.pg =pessoa.pg
    # db_pess.nome_guerra = pessoa.nome_guerra
    # db_pess.nome_completo = pessoa.nome_completo
    # db_pess.ult_promo = pessoa.ult_promo
    # db_pess.id_fab = pessoa.id_fab
    # db_pess.saram = pessoa.saram
    # db_pess.cpf = pessoa.cpf
    # db_pess.nasc = pessoa.nasc
    # db_pess.celular = pessoa.celular
    # db_pess.email_pess = pessoa.email_pess
    # db_pess.email_fab = pessoa.email_fab
    # db_pess.unidade = pessoa.unidade

    session.commit()
    session.refresh(db_pess)

    return {'detail': 'Atualizado com sucesso'}


@router.delete('/{pess_id}')
def delete_pessoa(pess_id: int, session: Session):
    query = select(Pessoa).where(Pessoa.id == pess_id)

    db_pess: Pessoa = session.scalar(query)

    if not db_pess:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    session.delete(db_pess)
    session.commit()

    return {'detail': 'Deletado com Sucesso'}

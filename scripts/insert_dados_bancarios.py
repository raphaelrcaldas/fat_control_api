"""
Script para inserir dados bancários em massa a partir de uma lista de
SARAMs. Faz lookup do usuário em `users` e cria o registro em
`dados_bancarios`. Pula SARAMs inexistentes e usuários que já possuem
dados (constraint UNIQUE em user_id).

Execução:
    cd api && uv run python scripts/insert_dados_bancarios.py
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios
from fcontrol_api.models.shared.users import User
from fcontrol_api.settings import Settings

# Mapeamento código FEBRABAN -> nome do banco (formato já usado no DB).
BANCOS = {
    '001': 'Banco do Brasil',
    '033': 'Santander',
    '077': 'Banco Inter',
    '104': 'Caixa Econômica Federal',
    '237': 'Bradesco',
    '260': 'Nu Pagamentos',
    '318': 'BMG',
    '336': 'C6 Bank',
    '341': 'Itaú',
}

# (saram, codigo_banco_raw, agencia, conta)
DADOS = [
    ('8023573', '033', '3677-3', '1098593-4'),
    ('2988879', '033', '3677', '01095276-9'),
    ('4287711', '033', '03380', '0010064786'),
    ('3503518', '104', '2387', '20423-3'),
    ('6073565', '033', '3838', '01083910-8'),
    ('3236544', '033', '3677', '01005718-7'),
    ('3714934', '104', '0215', '24361-0'),
    ('4109074', '341', '9664', '1196-3'),
    ('6350399', '237', '0415', '0150559-9'),
    ('4237544', '341', '7461', '32787-1'),
    ('4225740', '033', '3677', '01006094-5'),
    ('4359950', '001', '549-5', '78588-1'),
    ('6380085', '033', '3724', '01085907-6'),
    ('4199715', '033', '0026', '0134631-0'),
    ('6715052', '001', '0306-9', '99141-4'),
    ('4324897', '341', '8420', '04562-0'),
    ('3840247', '077', '0001', '671286-0'),
    ('6329888', '001', '1254-8', '27923-4'),
    ('3459403', '341', '7462', '10283-6'),
    ('3326039', '001', '35947', '73082-3'),
    ('4360087', '237', '7207', '783807-7'),
    ('6104339', '033', '3438', '02001679-3'),
    ('3373827', '033', '3823', '01004703-5'),
    ('6239765', '237', '2490', '651531-2'),
    ('3456072', '033', '3677', '02009190-8'),
    ('4199189', '341', '9651', '02802-0'),
    ('4094824', '033', '3677', '01084437-0'),
    ('6084737', '001', '4673-6', '80013-9'),
    ('4452798', '237', '3667', '1814-7'),
    ('4238958', '237', '2379-5', '464465'),
    ('3988694', '001', '3113-5', '11077-9'),
    ('2702428', '33', '3677', '01004841-9'),
    ('3130002', '001', '3111-9', '16646-4'),
    ('6808905', '237', '0415', '01521993'),
    ('6239390', '001', '04790', '1029967'),
    ('2762153', '001', '3113-5', '13621-2'),
    ('6526454', '033', '3677', '01090389-9'),
    ('6778615', '237', '2788', '0234929-9'),
    ('4125746', '033', '3677', '02009231-8'),
    ('4108817', '033', '3677', '01092317-2'),
    ('4329520', '001', '3113-5', '9781-0'),
    ('6714145', '001', '324-7', '202110-2'),
    ('6329713', '001', '3113-5', '8274-0'),
    ('6156819', '001', '3113-5', '123943'),
    ('4200250', '033', '3677', '02000662-7'),
    ('6447090', '033', '3677', '01089869-2'),
    ('7246854', '237', '415', '152734-7'),
    ('3285740', '077', '0001', '23323084-0'),
    ('6447198', '001', '3113-5', '48270-6'),
    ('4200020', '033', '3677', '01090913-2'),
    ('7285809', '001', '31135', '400467'),
    ('3511456', '336', '0001', '9057139-8'),
    ('6325092', '033', '3015', '01095043-9'),
    ('6239439', '001', '4315-X', '16601-4'),
    ('6422969', '341', '3937', '08484-0'),
    ('6450067', '033', '3449', '01074228-6'),
    ('6603335', '033', '3606', '01094202-1'),
    ('7014627', '001', '306-9', '60653-7'),
    ('4364864', '001', '3113-5', '10754-9'),
    ('4016548', '001', '0163-5', '68632-8'),
    ('4281136', '001', '3113', '319457'),
    ('3987957', '001', '04315', '15261-7'),
    ('6779697', '237', '2921-1', '28170-0'),
    ('3375943', '318', '0049', '15496000-9'),
    ('4304896', '033', '4831', '10835449'),
    ('2088690', '001', '3113-5', '7700-3'),
    ('4179471', '001', '1257-2', '145184-7'),
    ('6134203', '033', '3677-3', '1095124-9'),
    ('4227832', '033', '3677', '01089904-0'),
    ('4460871', '33', '3677', '01013567-2'),
    ('3101860', '104', '0215', '25984-2'),
    ('6577687', '033', '0966', '01022707-4'),
    ('4381386', '33', '3677', '01090983-3'),
    ('1482122', '104', '0542', '599862047-6'),
    ('3929507', '033', '3015', '01095856-1'),
    ('3373568', '033', '1660', '010113326'),
    ('4494113', '001', '03858', '0010832246'),
    ('2691540', '033', '3367', '01095279-0'),
    ('6628079', '237', '00129-5', '0004181441'),
    ('4494571', '237', '3667', '2198-9'),
    ('3236250', '001', '3113-5', '11525-8'),
    ('3418219', '001', '3113-5', '10.381-0'),
    ('3979814', '033', '3823', '010836505'),
    ('4240340', '341', '4479', '269195'),
    ('3490220', '237', '3677', '1681-0'),
    ('4408098', '033', '3668-4', '1001341-9'),
    ('6807550', '001', '3113-5', '1840-6'),
    ('6556477', '341', '3071', '487486'),
    ('6423191', '341', '1677', '62774-5'),
    ('4360257', '001', '3113-5', '95231-1'),
    ('4146107', '001', '0072-8', '50181-6'),
    ('3285472', '001', '3113-5', '56797-3'),
    ('4146590', '001', '0324-7', '441088-2'),
    ('3163989', '237', '1394', '5733-9'),
    ('6380000', '033', '3677', '01096290-2'),
    ('6447597', '001', '3113-5', '48226-9'),
    ('4381343', '033', '3438', '01096999-7'),
    ('3930734', '033', '3677', '01097214-5'),
    ('3988864', '033', '3823', '01006792-3'),
    ('6285821', '237', '519-3', '6984-1'),
    ('4004140', '341', '7818-2', '78180-4'),
    ('6068936', '001', '4315-0', '97250-9'),
    ('6323391', '033', '4223-4', '01042066-0'),
    ('3249891', '033', '3380-4', '001003398-4'),
    ('2831538', '237', '7028-9', '0005234-5'),
    ('6423159', '033', '3835', '01082532-8'),
    ('6432530', '104', '0440', '20520-7'),
    ('3988988', '033', '3461', '01001707-4'),
    ('4493478', '001', '0062-0', '47719-2'),
    ('6104940', '001', '3113-5', '36010-4'),
    ('4304047', '033', '3677', '01093219-4'),
    ('4239385', '033', '3677', '01084459-0'),
    ('7286228', '001', '3113-5', '401110'),
    ('4147901', '033', '3677', '01004586-3'),
    ('6133720', '001', '3113-5', '9630-X'),
    ('7493983', '001', '3113-5', '12976-3'),
    ('1073451', '001', '3113-5', '7465-9'),
    ('3299775', '033', '3893', '001002497-8'),
    ('7045212', '237', '415', '152597-2'),
    ('3987655', '033', '3677', '01005724-2'),
    ('6157505', '033', '3677', '01091400-2'),
    ('4305973', '001', '3113-5', '9994-5'),
    ('4219872', '001', '3113-5', '97617-2'),
    ('2888211', '341', '6893', '47047-3'),
    ('6103677', '001', '02663', '0001360558'),
    ('6104622', '341', '07024', '40532'),
    ('6198163', '033', '04831', '10838057'),
    ('7276362', '341', '0783', '78867-2'),
    ('4083326', '001', '03113', '106941'),
    ('6104622', '341', '07024', '040532'),
    ('7280688', '033', '3606', '01087121-1'),
    ('6423027', '001', '3113-5', '35918-1'),
    ('6900720', '336', '0001', '9635248-5'),
    ('7386389', '237', '415', '154500-0'),
    ('3455386', '341', '3071', '0040916-7'),
    ('6555357', '001', '2875-4', '98204-0'),
    ('7274882', '0260', '0001', '33486494-5'),
    ('6627951', '341', '6007', '39339-7'),
    ('6526926', '237', '3184', '30693'),
    ('4238966', '033', '03677', '010869751'),
    ('6169279', '033', '03677', '0010814115'),
    ('7274599', '033', '01522', '0010446960'),
    ('6668623', '001', '04673', '0000524948'),
    ('6017673', '033', '3677', '01005154-5'),
    ('6198597', '33', '4831', '01087758-8'),
    ('6435181', '001', '2663-8', '35951-3'),
    ('7540256', '341', '3606', '01088248-6'),
    ('6806481', '001', '306-9', '000056660-8'),
    ('6475698', '001', '3113-5', '000010933-9'),
    ('3284107', '033', '3677-3', '002003448-8'),
    ('7345895', '033', '3606-4', '001087390-7'),
    ('4144392', '001', '3113-5', '000005365-1'),
    ('6132766', '001', '2241-1', '000036411-8'),
    ('6493300', '001', '1570-9', '19048-9'),
    ('7275498', '033', '3606-4', '001087115-6'),
    ('3714098', '341', '321-9', '20609-5'),
    ('4144961', '033', '3677-3', '001094360-6'),
    ('4385756', '033', '3436-3', '001074708-1'),
    ('4201400', '033', '3380-4', '001083128-7'),
    ('6667490', '033', '3606-4', '001084804-6'),
    ('4172094', '341', '7461-6', '7466-3'),
    ('3929507', '033', '4257-9', '001083523-6'),
    ('6249019', '001', '306-9', '000039449-1'),
    ('7760450', '341', '6014', '30813-1'),
    ('6668798', '001', '3113', '000052418-2'),
    ('7503261', '033', '3677', '002007347-6'),
    ('7677898', '001', '3113', '000024208-X'),
    ('7632851', '001', '3113', '24050-8'),
    ('6197884', '001', '1845', '78427-3'),
    ('6905188', '237', '0507', '14494-0'),
    ('7550472', '001', '3113', '57266-7'),
]


def normalizar_codigo(raw: str) -> str:
    """'33' -> '033', '0260' -> '260', '001' -> '001'."""
    return f'{int(raw):03d}'


async def inserir_dados_bancarios():
    print('=' * 80)
    print('SCRIPT DE INSERÇÃO EM MASSA - DadosBancarios')
    print('=' * 80)
    print()

    settings = Settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Dedup defensivo: mantém primeira ocorrência por SARAM.
        unicos: dict[str, tuple[str, str, str, str]] = {}
        for saram, cod_raw, ag, conta in DADOS:
            if saram in unicos:
                continue
            unicos[saram] = (saram, cod_raw, ag, conta)

        total = len(unicos)
        sarams = list(unicos.keys())

        print(f'📋 Linhas de entrada: {len(DADOS)}')
        print(f'   ↳ SARAMs únicos: {total}')
        print()

        # Carrega usuários e dados bancários existentes em batch.
        print('🔍 Buscando usuários e dados existentes...')
        users_result = await session.execute(
            select(User.id, User.saram).where(User.saram.in_(sarams))
        )
        user_by_saram = {saram: uid for uid, saram in users_result.all()}

        existentes_result = await session.execute(
            select(DadosBancarios.user_id).where(
                DadosBancarios.user_id.in_(user_by_saram.values())
            )
        )
        user_ids_com_dados = set(existentes_result.scalars().all())

        print(f'   ✓ {len(user_by_saram)} usuários encontrados')
        print(f'   ✓ {len(user_ids_com_dados)} já possuem dados bancários')
        print()

        inseridos: list[str] = []
        nao_encontrados: list[str] = []
        ja_existiam: list[str] = []
        codigo_desconhecido: list[tuple[str, str]] = []

        print('⚙️  Processando...')
        with tqdm(
            total=total, desc='Inserindo', unit='reg', ncols=100
        ) as pbar:
            for saram, cod_raw, agencia, conta in unicos.values():
                pbar.set_description(f'🔄 SARAM {saram}')

                user_id = user_by_saram.get(saram)
                if user_id is None:
                    nao_encontrados.append(saram)
                    pbar.update(1)
                    continue

                if user_id in user_ids_com_dados:
                    ja_existiam.append(saram)
                    pbar.update(1)
                    continue

                codigo = normalizar_codigo(cod_raw)
                banco = BANCOS.get(codigo)
                if banco is None:
                    codigo_desconhecido.append((saram, codigo))
                    banco = codigo

                session.add(
                    DadosBancarios(
                        user_id=user_id,
                        banco=banco,
                        codigo_banco=codigo,
                        agencia=agencia,
                        conta=conta,
                    )
                )
                inseridos.append(saram)
                # Reserva user_id para evitar duplicar caso DADOS contenha
                # outro registro com mesmo SARAM mais à frente.
                user_ids_com_dados.add(user_id)
                pbar.update(1)

        print()
        print('💾 Salvando alterações...')
        await session.commit()
        print('   ✓ Commit concluído.')

        print()
        print('=' * 80)
        print('RELATÓRIO FINAL')
        print('=' * 80)
        print(f'Total processado:           {total}')
        print(f'✅ Inseridos:                {len(inseridos)}')
        print(f'⏭️  SARAMs não encontrados:  {len(nao_encontrados)}')
        print(f'⏭️  Já possuíam dados:       {len(ja_existiam)}')
        print(f'⚠️  Códigos desconhecidos:   {len(codigo_desconhecido)}')
        print()

        if nao_encontrados:
            print('SARAMs NÃO ENCONTRADOS em users:')
            print('-' * 80)
            for saram in sorted(nao_encontrados):
                print(f'  {saram}')
            print()

        if ja_existiam:
            print('SARAMs QUE JÁ POSSUÍAM dados bancários:')
            print('-' * 80)
            for saram in sorted(ja_existiam):
                print(f'  {saram}')
            print()

        if codigo_desconhecido:
            print('CÓDIGOS DE BANCO sem mapeamento (gravados como código):')
            print('-' * 80)
            for saram, codigo in codigo_desconhecido:
                print(f'  SARAM {saram} -> código {codigo}')
            print()

        print('=' * 80)

    await engine.dispose()


if __name__ == '__main__':
    print()
    inicio = datetime.now()
    asyncio.run(inserir_dados_bancarios())
    fim = datetime.now()
    print()
    print(f'⏱️  Tempo total: {(fim - inicio).total_seconds():.2f}s')
    print()

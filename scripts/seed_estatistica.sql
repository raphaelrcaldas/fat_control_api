-- Seed: tabelas do schema estatistica (esforço aéreo, etapas, missões)
-- Uso: podman exec fcontrol_db psql -U username -d app_db -f /path/seed_estatistica.sql
-- Ou:  cat scripts/seed_estatistica.sql | podman exec -i fcontrol_db psql -U username -d app_db

BEGIN;

-- Limpa dados existentes (ordem respeitando FKs)
TRUNCATE
    estatistica.trip_etapa,
    estatistica.oi_etapa,
    estatistica.etapas,
    estatistica.missao,
    estatistica.tipo_missao,
    estatistica.esf_aer_aloc_hist,
    estatistica.esf_aer_alocado,
    estatistica.esf_aer
CASCADE;

-- Reinicia sequences
ALTER SEQUENCE estatistica.esf_aer_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.esf_aer_alocado_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.esf_aer_aloc_hist_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.missao_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.tipo_missao_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.etapas_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.oi_etapa_id_seq RESTART WITH 1;
ALTER SEQUENCE estatistica.trip_etapa_id_seq RESTART WITH 1;

---------------------------------------
-- 1. Esforços Aéreos
---------------------------------------
INSERT INTO estatistica.esf_aer (tipo, modelo, grupo, prog, sub_prog, aplicacao) VALUES
('COMAE',   'PAOE',   'SPAOE', 'AOE',      NULL,    NULL),     -- 1
('COMAE',   'PAOE',   'SPAOE', 'ZIDA',     '41',    NULL),     -- 2
('COMAE',   'PEO',    'SPMAS', 'DECEA',    NULL,    NULL),      -- 3
('COMAE',   'PEO',    'SPMAS', 'EVAM',     NULL,    NULL),      -- 4
('COMAE',   'PEO',    'SPMAS', 'FAB-TAL',  NULL,    NULL),      -- 5
('COMAE',   'PEO',    'SPMAS', 'FUMACA',   NULL,    NULL),      -- 6
('COMAE',   'PEO',    'SPMAS', 'GABAER',   NULL,    NULL),      -- 7
('COMAE',   'PEO',    'SPMAS', 'LTN',      NULL,    NULL),      -- 8
('COMAE',   'PEO',    'SPMAS', 'URNA',     NULL,    NULL),      -- 9
('COMAE',   'PMC-MB', 'SPMC',  'MB-TAL',   NULL,    NULL),      -- 10
('COMAE',   'PMC-MB', 'SPMC',  'PROANTAR', NULL,    NULL),      -- 11
('COMAE',   'PMC-MD', 'SPMC',  'MD-TAL',   NULL,    NULL),      -- 12
('COMPREP', 'PRPO',   'SPREP', 'ARCANJO',  NULL,    NULL),      -- 13
('COMPREP', 'PRPO',   'SPREP', 'CARRANCA', NULL,    NULL),      -- 14
('COMPREP', 'PRPO',   'SPREP', 'DBNQR',    NULL,    NULL),      -- 15
('COMPREP', 'PRPO',   'SPREP', 'FORMA',    '390',   NULL),      -- 16
('COMPREP', 'PRPO',   'SPREP', 'LA GORDO', NULL,    NULL),      -- 17
('COMPREP', 'PRPO',   'SPREP', 'OPFM',     NULL,    NULL),      -- 18
('COMPREP', 'PRPO',   'SPREP', 'REVO-CA',  NULL,    NULL),      -- 19
('COMPREP', 'PRPO',   'SPREP', 'SLOP',     NULL,    NULL),      -- 20
('DCTA',    'PACTA',  'OPR',   'AVOP',     'F-39E', '2026'),    -- 21
('DCTA',    'PACTA',  'OPR',   'CAXIRI',   'KC390', NULL),      -- 22
('DCTA',    'PACTA',  'OPR',   'ZEUS',     '2026',  NULL);      -- 23

---------------------------------------
-- 2. Alocação por esforço aéreo (2026, valores em minutos)
---------------------------------------
INSERT INTO estatistica.esf_aer_alocado (esfaer_id, ano_ref, alocado) VALUES
(1,  2026, 10200),  -- AOE: 170h
(2,  2026, 2400),   -- ZIDA 41: 40h
(3,  2026, 1200),   -- DECEA: 20h
(4,  2026, 1200),   -- EVAM: 20h
(5,  2026, 14280),  -- FAB-TAL: 238h
(6,  2026, 300),    -- FUMACA: 5h
(7,  2026, 3000),   -- GABAER: 50h
(8,  2026, 0),      -- LTN: 0h
(9,  2026, 600),    -- URNA: 10h
(10, 2026, 1500),   -- MB-TAL: 25h
(11, 2026, 6000),   -- PROANTAR: 100h
(12, 2026, 1200),   -- MD-TAL: 20h
(13, 2026, 120),    -- ARCANJO: 2h
(14, 2026, 1200),   -- CARRANCA: 20h
(15, 2026, 180),    -- DBNQR: 3h
(16, 2026, 1800),   -- FORMA 390: 30h
(17, 2026, 1320),   -- LA GORDO: 22h
(18, 2026, 1080),   -- OPFM: 18h
(19, 2026, 2100),   -- REVO-CA: 35h
(20, 2026, 600),    -- SLOP: 10h
(21, 2026, 300),    -- AVOP F-39E: 5h
(22, 2026, 600),    -- CAXIRI KC390: 10h
(23, 2026, 6000);   -- ZEUS 2026: 100h

---------------------------------------
-- 3. Histórico de alterações de alocação
---------------------------------------
INSERT INTO estatistica.esf_aer_aloc_hist (esf_aer_aloc_id, aloc_hist, timestamp) VALUES
-- FAB-TAL: era 15000 (250h), mudou para 14280 (238h)
(5, 15000, '2026-01-10 14:30:00'),
(5, 14280, '2026-02-05 09:15:00'),
-- PROANTAR: era 7200 (120h), mudou para 6000 (100h)
(11, 7200, '2026-01-08 10:00:00'),
(11, 6000, '2026-01-20 16:45:00'),
-- LTN: era 780 (13h), zerou
(8, 780, '2026-01-05 08:00:00'),
(8, 0,   '2026-02-01 11:30:00');

---------------------------------------
-- 4. Tipos de missão
---------------------------------------
INSERT INTO estatistica.tipo_missao (cod, "desc") VALUES
('INS', 'Instrução'),
('ADM', 'Administrativo'),
('OPE', 'Operacional'),
('TRN', 'Treinamento');

---------------------------------------
-- 5. Missões
---------------------------------------
INSERT INTO estatistica.missao (titulo, obs) VALUES
('PROANTAR 2026',    'Apoio à Operação Antártica'),
('FAB-TAL JAN/26',   NULL),
('FORMA 390 FEV/26', 'Formatura KC-390'),
('CARRANCA FEV/26',  NULL);

---------------------------------------
-- 6. Etapas (voos)
-- tvoo é coluna computed (arr - dep em minutos)
-- Aeronaves reais: 2860, 2857, 2859
-- Aeródromos reais: SBGL, SBAF, SBSM, SBAN, SBNT, SBCG, SBMN
---------------------------------------
INSERT INTO estatistica.etapas
    (missao_id, data, origem, destino, dep, arr, anv, pousos, tow, pax, carga, comb, sagem, parte1, obs)
VALUES
-- Missão 1: PROANTAR
(1, '2026-01-15', 'SBGL', 'SBAF', '08:00', '08:40', '2860', 1, 62000, 5,  200,  3500, false, false, NULL),           -- 1
(1, '2026-01-15', 'SBAF', 'SBGL', '10:30', '11:15', '2860', 1, 60000, 5,  100,  3200, false, false, NULL),           -- 2
(1, '2026-01-20', 'SBGL', 'SBSM', '07:00', '09:30', '2860', 1, 72000, 15, 500,  8000, true,  true,  'Apoio log.'), -- 3
-- Missão 2: FAB-TAL
(2, '2026-01-10', 'SBAF', 'SBAN', '09:00', '11:00', '2857', 1, 65000, 3,  0,    6000, false, false, NULL),           -- 4
(2, '2026-01-10', 'SBAN', 'SBAF', '14:00', '16:10', '2857', 1, 63000, 3,  0,    5500, false, false, NULL),           -- 5
(2, '2026-02-05', 'SBAF', 'SBGL', '08:30', '09:10', '2860', 2, 61000, 8,  300,  3000, false, false, NULL),           -- 6
(2, '2026-02-05', 'SBGL', 'SBNT', '10:00', '13:20', '2860', 1, 70000, 12, 400,  9000, true,  true,  NULL),           -- 7
-- Missão 3: FORMA 390
(3, '2026-02-10', 'SBAF', 'SBCG', '06:00', '08:30', '2859', 1, 68000, 4,  0,    7000, false, false, NULL),           -- 8
(3, '2026-02-11', 'SBCG', 'SBAF', '09:00', '11:25', '2859', 1, 66000, 4,  0,    6500, false, false, NULL),           -- 9
-- Missão 4: CARRANCA
(4, '2026-02-18', 'SBAF', 'SBMN', '05:00', '09:30', '2860', 1, 72000, 20, 800, 10000, true,  true,  'Desloc. MN'), -- 10
(4, '2026-02-20', 'SBMN', 'SBAF', '06:00', '10:25', '2860', 1, 71000, 18, 600,  9500, true,  true,  NULL);           -- 11

---------------------------------------
-- 7. OI por Etapa (vincula etapas a esforços aéreos)
---------------------------------------
INSERT INTO estatistica.oi_etapa (etapa_id, esf_aer_id, tvoo, reg, tipo_missao_id) VALUES
-- PROANTAR (esf_aer_id=11)
(1,  11, 40,  'd', 3),   -- SBGL-SBAF 40min OPE
(2,  11, 45,  'd', 3),   -- SBAF-SBGL 45min OPE
(3,  11, 150, 'd', 3),   -- SBGL-SBSM 150min OPE
-- FAB-TAL (esf_aer_id=5)
(4,  5,  60,  'd', 1),   -- SBAF-SBAN 60min INS
(4,  5,  60,  'd', 4),   -- mesma etapa: 60min TRN (2 OIs)
(5,  5,  130, 'd', 1),   -- SBAN-SBAF 130min INS
(6,  5,  40,  'd', 2),   -- SBAF-SBGL 40min ADM
(7,  5,  200, 'd', 3),   -- SBGL-SBNT 200min OPE
-- FORMA 390 (esf_aer_id=16)
(8,  16, 150, 'd', 4),   -- SBAF-SBCG 150min TRN
(9,  16, 145, 'd', 4),   -- SBCG-SBAF 145min TRN
-- CARRANCA (esf_aer_id=14)
(10, 14, 270, 'd', 3),   -- SBAF-SBMN 270min OPE
(11, 14, 265, 'd', 3);   -- SBMN-SBAF 265min OPE

---------------------------------------
-- 8. Tripulação por etapa
-- trip_id referencia tripulantes existentes (1-19)
---------------------------------------
INSERT INTO estatistica.trip_etapa (etapa_id, func, func_bordo, trip_id) VALUES
-- PROANTAR
(1,  'mc', 'P1', 1),  (1,  'mc', 'P2', 2),
(2,  'mc', 'P1', 1),  (2,  'mc', 'P2', 2),
(3,  'mc', 'P1', 1),  (3,  'mc', 'P2', 2),  (3,  'oe', 'MS', 3),
-- FAB-TAL
(4,  'mc', 'P1', 6),  (4,  'mc', 'P2', 9),
(5,  'mc', 'P1', 6),  (5,  'mc', 'P2', 9),
(6,  'mc', 'P1', 1),  (6,  'mc', 'P2', 12),
(7,  'mc', 'P1', 1),  (7,  'mc', 'P2', 12), (7,  'oe', 'MS', 13),
-- FORMA 390
(8,  'mc', 'P1', 15), (8,  'mc', 'P2', 18),
(9,  'mc', 'P1', 15), (9,  'mc', 'P2', 18),
-- CARRANCA
(10, 'mc', 'P1', 1),  (10, 'mc', 'P2', 2),  (10, 'oe', 'MS', 19),
(11, 'mc', 'P1', 1),  (11, 'mc', 'P2', 2),  (11, 'oe', 'MS', 19);

COMMIT;

-- Seed: resource + permissões granulares da aba Passaportes (módulo Inteligência)
-- Cria o resource 'passaportes', as 4 permissões (view/create/update/delete)
-- e vincula todas à role 'inteligencia'. Idempotente (WHERE NOT EXISTS):
-- pode ser reexecutado sem duplicar linhas.
--
-- Uso (DEV primeiro, depois PROD):
--   podman exec -i fcontrol_db psql -U username -d app_db -f - < scripts/seed_passaportes_perms.sql
-- Ou:
--   cat scripts/seed_passaportes_perms.sql | podman exec -i fcontrol_db psql -U username -d app_db
--
-- ATENÇÃO: validar em dev (fcontrol_db) antes de aplicar em produção (Supabase).

BEGIN;

---------------------------------------
-- 1. Resource
---------------------------------------
INSERT INTO security.resources (name, description)
SELECT 'passaportes', 'Passaportes e vistos de tripulantes (Inteligência)'
WHERE NOT EXISTS (
    SELECT 1 FROM security.resources WHERE name = 'passaportes'
);

---------------------------------------
-- 2. Permissões (view / create / update / delete)
---------------------------------------
INSERT INTO security.permissions (resource_id, name, description)
SELECT r.id, p.name, p.description
FROM security.resources r
CROSS JOIN (
    VALUES
        ('view',   'Listar/visualizar passaportes'),
        ('create', 'Cadastrar passaporte novo'),
        ('update', 'Editar passaporte existente'),
        ('delete', 'Remover passaporte')
) AS p(name, description)
WHERE r.name = 'passaportes'
  AND NOT EXISTS (
      SELECT 1 FROM security.permissions ep
      WHERE ep.resource_id = r.id AND ep.name = p.name
  );

---------------------------------------
-- 3. Vínculo das permissões à role 'inteligencia'
---------------------------------------
INSERT INTO security.role_permissions (role_id, permission_id)
SELECT ro.id, pe.id
FROM security.roles ro
JOIN security.permissions pe ON pe.name IN ('view', 'create', 'update', 'delete')
JOIN security.resources re ON re.id = pe.resource_id AND re.name = 'passaportes'
WHERE ro.name = 'inteligencia'
  AND NOT EXISTS (
      SELECT 1 FROM security.role_permissions rp
      WHERE rp.role_id = ro.id AND rp.permission_id = pe.id
  );

COMMIT;

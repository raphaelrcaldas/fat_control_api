-- Seed: resource + permissões granulares das IMAGENS de passaporte/visto
-- (módulo Inteligência). Cria o resource 'passaporte.image', as 4 permissões
-- (view/create/update/delete) e vincula todas à role 'inteligencia'.
-- Idempotente (WHERE NOT EXISTS): pode ser reexecutado sem duplicar linhas.
--
-- As imagens são um recurso PRÓPRIO, desacoplado de 'passaportes' (dados
-- textuais), permitindo conceder acesso às imagens sem dar acesso de edição
-- dos campos (e vice-versa).
--
-- Uso (DEV primeiro, depois PROD):
--   podman exec -i fcontrol_db psql -U username -d app_db -f - < scripts/seed_passaporte_image_perms.sql
-- Ou:
--   cat scripts/seed_passaporte_image_perms.sql | podman exec -i fcontrol_db psql -U username -d app_db
--
-- ATENÇÃO: validar em dev (fcontrol_db) antes de aplicar em produção (Supabase).

BEGIN;

---------------------------------------
-- 1. Resource
---------------------------------------
INSERT INTO security.resources (name, description)
SELECT 'passaporte.image', 'Imagens (JPG) de passaporte e visto (Inteligência)'
WHERE NOT EXISTS (
    SELECT 1 FROM security.resources WHERE name = 'passaporte.image'
);

---------------------------------------
-- 2. Permissões (view / create / update / delete)
---------------------------------------
INSERT INTO security.permissions (resource_id, name, description)
SELECT r.id, p.name, p.description
FROM security.resources r
CROSS JOIN (
    VALUES
        ('view',   'Visualizar imagens de passaporte/visto'),
        ('create', 'Enviar a primeira imagem de um tipo'),
        ('update', 'Substituir imagem existente'),
        ('delete', 'Remover imagem')
) AS p(name, description)
WHERE r.name = 'passaporte.image'
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
JOIN security.resources re ON re.id = pe.resource_id AND re.name = 'passaporte.image'
WHERE ro.name = 'inteligencia'
  AND NOT EXISTS (
      SELECT 1 FROM security.role_permissions rp
      WHERE rp.role_id = ro.id AND rp.permission_id = pe.id
  );

COMMIT;

-- ══════════════════════════════════════════════════════
--  LINCE — Setup de base de datos en Supabase
--  Corre este SQL en: Supabase → SQL Editor → New query
-- ══════════════════════════════════════════════════════

-- Tabla principal de conversaciones
CREATE TABLE IF NOT EXISTS conversaciones (
  id         uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id text        NOT NULL,
  role       text        NOT NULL CHECK (role IN ('user', 'assistant')),
  content    text        NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Índices para búsquedas rápidas por sesión y fecha
CREATE INDEX IF NOT EXISTS idx_conversaciones_session ON conversaciones(session_id);
CREATE INDEX IF NOT EXISTS idx_conversaciones_fecha   ON conversaciones(created_at);

-- Política de seguridad: solo lectura/escritura desde el servidor (service role)
ALTER TABLE conversaciones ENABLE ROW LEVEL SECURITY;

-- Permitir acceso con la anon key (para el backend)
CREATE POLICY "allow_all" ON conversaciones
  FOR ALL
  USING (true)
  WITH CHECK (true);

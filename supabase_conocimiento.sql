-- ══════════════════════════════════════════════════════
--  LINCE — Base de conocimiento REAL de la UAdeO
--  Supabase → SQL Editor → New query → Run
-- ══════════════════════════════════════════════════════

-- Crear tabla si no existe
CREATE TABLE IF NOT EXISTS conocimiento (
  id         uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  categoria  text        NOT NULL,
  titulo     text        NOT NULL,
  contenido  text        NOT NULL,
  activo     boolean     DEFAULT true,
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conocimiento_categoria ON conocimiento(categoria);
CREATE INDEX IF NOT EXISTS idx_conocimiento_activo    ON conocimiento(activo);

ALTER TABLE conocimiento ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "allow_all" ON conocimiento;
CREATE POLICY "allow_all" ON conocimiento FOR ALL USING (true) WITH CHECK (true);

-- Limpiar datos anteriores e insertar los reales
DELETE FROM conocimiento;

INSERT INTO conocimiento (categoria, titulo, contenido) VALUES

('identidad', 'Información general de la UAdeO',
'Nombre completo: Universidad Autónoma de Occidente. Abreviatura: UAdeO. Ubicación: Boulevard Enrique Sánchez Alonso número 1833, Desarrollo Urbano Tres Ríos, C.P. 80298, Culiacán, Sinaloa. Tipo: Universidad pública autónoma del estado de Sinaloa, México. Fundación: 1978. Lema: "Por el progreso de Sinaloa". Mascota: El Lince. Se les conoce a los universitarios como "Linces".'),

('identidad', 'Datos relevantes',
'En 2022 la institución concentró una matrícula mayoritaria de mujeres (61.7%) con enfoque en ciencias sociales, derecho y salud. Se han realizado consultas para la reforma de su Ley Orgánica y destacan por cursos de sensibilización para el servicio social. Sitio web oficial: www.udo.mx. Facebook: Universidad de Occidente. Instagram: @uado_oficial.'),

('ubicaciones', 'Edificios y locaciones del campus Culiacán',
'Edificio D, Edificio E, Edificio H, Edificio P, Edificio J, Edificio F, Edificio K, Edificio C, Rectoría UAdeO, Teatro Lince de la Universidad, Biblioteca Gonzalo Armienta, Fuerza Académica de Occidente, CIC Centro Integral de Comunicación, CELE UAdeO Culiacán, Auditorio Julio Ibarra, Campo de fútbol UAdeO, Campo de béisbol UAdeO, Campo de fútbol americano UAdeO.'),

('campus', 'Sedes y campus de la UAdeO',
'Campus Culiacán (Culiacán, Sinaloa), Campus Los Mochis (Los Mochis, Sinaloa), Campus Mazatlán (Mazatlán, Sinaloa), Campus Guamúchil (Guamúchil, Sinaloa), Campus Guasave (Guasave, Sinaloa), Campus Los Álamos (Los Álamos, Sinaloa).'),

('carreras', 'Carreras de Ingeniería y Tecnología',
'Ingeniería en Sistemas Computacionales, Ingeniería Industrial, Ingeniería Civil, Ingeniería en Electrónica y Comunicaciones, Ingeniería en Mecatrónica.'),

('carreras', 'Carreras Económico-Administrativas',
'Licenciatura en Administración de Empresas, Licenciatura en Contaduría Pública, Licenciatura en Comercio Internacional y Aduanas, Licenciatura en Turismo.'),

('carreras', 'Carreras de Ciencias Sociales y Humanidades',
'Licenciatura en Derecho, Licenciatura en Comunicación, Licenciatura en Psicología, Licenciatura en Trabajo Social, Licenciatura en Pedagogía.'),

('carreras', 'Carreras de Ciencias de la Salud',
'Licenciatura en Enfermería, Licenciatura en Nutrición.'),

('posgrados', 'Posgrados disponibles',
'Maestría en Administración, Maestría en Ciencias de la Computación, Maestría en Derecho, Doctorado en Ciencias Administrativas. Verifica la oferta actualizada en www.udo.mx.'),

('admision', 'Proceso de admisión',
'Examen de admisión: EXANI-II (CENEVAL) o prueba propia según convocatoria. Periodos de inscripción: Enero-Febrero para el semestre agosto, y Agosto-Septiembre para el semestre enero. Documentos requeridos: Certificado de preparatoria, CURP, acta de nacimiento, fotografías. Registro en el portal oficial de la UAdeO.'),

('calendario', 'Calendario escolar',
'Semestre Enero-Junio: inicia en enero, termina en junio. Semestre Agosto-Diciembre: inicia en agosto, termina en diciembre. Semanas de exámenes finales: últimas 2 semanas de cada semestre. Horario administrativo general: 9:00 AM a 7:00 PM.'),

('servicios', 'Servicios estudiantiles',
'Biblioteca universitaria Gonzalo Armienta (física y digital), Servicio médico universitario, Deportes y actividades culturales (fútbol, béisbol, fútbol americano), Bolsa de trabajo universitaria, Servicio de tutorías, Centro de idiomas CELE.'),

('becas', 'Becas disponibles',
'PRONABES, Beca de excelencia académica, Beca de apoyo económico, Beca de movilidad estudiantil. Para más información acude al Departamento de Becas de tu campus.'),

('tramites', 'Trámites comunes',
'Credencial estudiantil: Departamento de Control Escolar. Kardex y constancias: Ventanilla de Control Escolar. Servicio social: 180 horas obligatorias, acude al Departamento de Servicio Social. Prácticas profesionales: Coordinación de cada programa. Titulación: tesis, proyecto de investigación, examen EGEL o cursos de titulación.'),

('reglamento', 'Reglamento estudiantil',
'Asistencia mínima: 80% para tener derecho a examen ordinario. Calificación mínima aprobatoria: 7.0 en escala del 0 al 10. Oportunidades de examen: Ordinario, Extraordinario y Título de Suficiencia. Las faltas injustificadas acumuladas pueden resultar en baja temporal.'),

('instrucciones', 'Cómo usar a Lince correctamente',
'Saluda para iniciar. Escribe preguntas claras y directas, una a la vez. Usa lenguaje sencillo y palabras clave como: credencial, servicio social, carreras, edificio, biblioteca. Evita abreviaciones como "k onda kardex". Si no obtienes lo que buscas, reformula tu pregunta. Lince es una herramienta de apoyo; para trámites importantes acude a Servicios Escolares o tu coordinador de carrera.');

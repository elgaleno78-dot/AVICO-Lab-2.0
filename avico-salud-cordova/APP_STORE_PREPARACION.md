# AVICO® Salud — preparación para App Store

**Estado:** proyecto fuente preparado parcialmente. **No existe aún IPA firmada ni envío a App Store Connect.**

## Datos preliminares

- Nombre visible: AVICO Salud
- Identificador propuesto: mx.com.avicosalud.mobile (comprobar disponibilidad y titularidad)
- Versión: 0.1.0, compilación 1
- Categoría sugerida: Educación o Medicina (determinar según funciones definitivas)
- Idioma: español
- Portal: https://avico-salud-ecosistema.onrender.com
- Compatibilidad: iPhone; probar específicamente iPhone SE y otros tamaños.

## Bloqueadores antes de enviar

1. Mac con Xcode compatible, cuenta activa de Apple Developer Program y acceso a App Store Connect.
2. Compilar `npm install`, `npx cordova platform add ios`, `npx cordova build ios --release`; abrir el proyecto en Xcode, configurar Team y firma, archivar y subir a App Store Connect.
3. Crear iconos PNG para iOS, pantalla de lanzamiento y capturas reales de iPhone. No se incluyen todavía.
4. Probar navegación y enlaces en dispositivos reales, cierre de sesión, accesibilidad, offline, botón de regreso y enlaces externos.
5. Definir URL pública de política de privacidad, contacto de soporte y respuestas de privacidad de App Store según las prácticas reales de **cada** servicio enlazado. No declarar «no se recopilan datos» sin auditar analítica, inicios de sesión y apps clínicas.
6. Revisar cumplimiento de privacidad, datos de salud y términos de las apps clínicas; presentar descargos médicos claros y no utilizar información clínica sensible sin medidas apropiadas.
7. Revisar requisito de funcionalidad mínima: un simple sitio web empaquetado puede ser rechazado por Apple. Añadir capacidades propias útiles de iOS antes del envío.
8. Preparar descripción, palabras clave, edad, clasificación, derechos de marca y material promocional.
9. Enviar a TestFlight, completar pruebas, resolver fallos y solo entonces solicitar revisión de App Store.

**Este proyecto no modifica los datos ni el código de las apps enlazadas.**

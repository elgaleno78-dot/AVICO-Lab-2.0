# AVICO® Salud — aplicación móvil Cordova

Proyecto **independiente** de AVICO® Salud en Render y de las aplicaciones clínicas.

## Estado real

- Configuración inicial Cordova: preparada.
- Pantalla de arranque: preparada; abre el portal alojado en Render.
- APK y AAB Android: **aún no compilados ni probados**.
- iOS: requiere macOS y Xcode; **no compilado**.
- Los módulos externos necesitan conexión a internet.

## Compilación Android (equipo de desarrollo)

1. Instalar Node.js, JDK compatible, Android Studio y Android SDK.
2. Desde esta carpeta ejecutar `npm install`.
3. Comprobar dependencias con `npm run requirements`.
4. Ejecutar `npm run build:android`.
5. Probar el APK de depuración en un dispositivo real. Revisar el botón Atrás, enlaces externos, permisos y conectividad.
6. Para publicación, preparar un AAB de lanzamiento firmado y cumplir los requisitos vigentes de Google Play.

## Compilación iOS

En macOS con Xcode, ejecutar `npm install` y `npm run build:ios`. Se necesita revisar políticas de App Store, navegación, permisos y privacidad.

## Seguridad

La aplicación es un contenedor de navegación, **no un almacén de datos clínicos**. La aplicación de presión arterial y AVICO® QBL siguen alojadas por separado. Evitar incorporar datos de pacientes al paquete.

## Revisión pendiente

Validar la experiencia nativa y los requisitos de publicación: un simple contenedor web puede no cumplir las políticas de calidad de las tiendas. Se recomienda probar primero la PWA.

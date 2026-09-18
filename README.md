# AVICO Lab 2.0

Laboratorio viviente de análisis retrospectivo para integrar archivos Excel, reconstruir la actividad del servicio por fecha/turno/médico y generar hallazgos operativos basados en datos.

## MVP
- Carga múltiple de Excel (.xlsx/.xls)
- Normalización automática de columnas
- Catálogo maestro de médicos
- Línea temporal retrospectiva
- Resumen estadístico dinámico
- Exploración por médico, turno, fecha y variable
- Preparado para desplegar en Render

## Despliegue
Render puede ejecutar este repositorio con:

```
pip install -r requirements.txt
gunicorn app:server
```

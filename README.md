# Seguimiento de Contratos

Aplicación web (Flask) para gestionar contratos vigentes, por vencer y vencidos, con carga de archivos Excel y filtrado por Línea, Cliente y Denominación. Visualiza los vencimientos más próximos.

## Características
- Carga de Excel (.xlsx/.xls) y lectura de la hoja `DDBB` (con tolerancia por nombre similar).
- Detección difusa de la columna de representante (`KAM / Repr` o similar) y filtrado para `PABLO YEVENES` (o coincidencias similares).
- Extracción de columnas relevantes: `Linea`, `Nom_Cliente`, `Nº de pedido`, `Denominación`, `Inicio de validez`, `Fin de validez`.
- Filtros por Línea, Cliente y Denominación.
- Gráfico de barras de vencimientos (Vencidos, 0-30, 31-60, 61-90, 90+ días) y lista de próximos vencimientos.

## Requisitos
- Python 3.11

## Instalación local
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Abre en el navegador: http://localhost:5000

## Estructura
```
contratos-tracker/
├─ app.py
├─ requirements.txt
├─ Procfile
├─ runtime.txt
├─ templates/
│  └─ index.html
├─ static/
│  ├─ main.js
│  └─ styles.css
└─ .gitignore
```

## Uso
1. Sube el archivo Excel (se buscará la hoja `DDBB`).
2. La app localizará la columna de `KAM / Repr` o similar y filtrará por `PABLO YEVENES`.
3. Se mostrarán los contratos y los filtros para Línea, Cliente y Denominación.
4. Visualiza el gráfico de vencimientos y los próximos a vencer.

## Despliegue en Railway
1. Crea un repositorio en GitHub y sube este proyecto.
2. En Railway, crea un nuevo proyecto "Deploy from GitHub" y selecciona el repositorio.
3. Railway detectará el `Procfile`. Configura la variable `PORT` si es necesario (Railway la proporciona automáticamente).
4. (Opcional) Define `SECRET_KEY` en variables de entorno.

## Notas
- La app intenta hacer matching difuso de nombres de columnas (acentos, variantes, etc.).
- Si no encuentra registros del representante objetivo, se mostrará un mensaje de error.
- Límite de subida: 20MB por archivo.

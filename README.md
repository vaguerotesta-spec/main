# Mi Finanzas - API de Seguimiento Financiero Personal

API y dashboard para organizar tus finanzas mensuales con soporte para pesos argentinos (ARS) y dólares (USD) con conversión al dólar blue.

## Funcionalidades

- **Períodos mensuales** con cotización de dólar blue configurable
- **Ingresos y gastos** en ARS y USD con conversión automática
- **Gastos fijos precargados**: alquiler, expensas, maestría, EPEC, fondos, etc.
- **Dashboard visual** con resumen, balance y barra de progreso
- **Paleta de colores** beige, greige, blanco, gris y rosados

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
uvicorn app.main:app --reload
```

Abrí http://localhost:8000 para ver el dashboard.

## API Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/periods` | Listar períodos |
| POST | `/api/periods` | Crear período |
| PATCH | `/api/periods/{id}` | Actualizar período |
| DELETE | `/api/periods/{id}` | Eliminar período |
| GET | `/api/transactions` | Listar transacciones |
| POST | `/api/transactions` | Crear transacción |
| PATCH | `/api/transactions/{id}` | Actualizar transacción |
| DELETE | `/api/transactions/{id}` | Eliminar transacción |
| GET | `/api/summary/{period_id}` | Resumen mensual |
| POST | `/api/periods/{id}/seed-defaults` | Cargar gastos fijos |
| GET | `/api/categories` | Listar categorías |

## Datos predeterminados

### Ingresos
- Salario USD: US$ 1,750
- Salario ARS: $ 400,000

### Gastos fijos
- Alquiler: $ 915,000
- Expensas: $ 170,000
- Expensas cochera: $ 60,000
- Maestría: $ 250,000
- EPEC: $ 55,000
- Fondo común pareja: $ 100,000
- Fondo jubilación: US$ 100

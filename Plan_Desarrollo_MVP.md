¡Listo! Aquí tienes un **plan de ingeniería de software completo** para tu **SaaS de panaderías** (recetas, producción, inventario con lotes/vida útil y mermas, ventas/POS, CPE/GRE, pagos locales, reportes), incluyendo **requisitos funcionales y no funcionales**, **modelo de dominio y datos**, **estrategia multi-tenant con RLS**, y **todos los diagramas clave en Mermaid** (con guía rápida de uso).

---

# 1) Requisitos funcionales (agrupados por dominio)

## 1.1 Tenancy & usuarios

* Alta/baja/edición de **panaderías (tenants)** con subdominio, plan, branding.
* Gestión de **usuarios** y **roles** por tenant: `OWNER`, `MANAGER`, `CASHIER`, `BAKER`, `STOREKEEPER`.
* Inicio de sesión (OIDC / Supabase Auth) y **scoping por tenant** en cada petición.
* Panel de **admin global** (tuyo) para crear tenants, ver consumo, bloquear/re-activar.

## 1.2 Catálogo y recetas

* CRUD de **productos**: terminados, insumos y empaques; UOM; impuestos; precio(s).
* **Recetas** por porcentaje panadero; rendimiento esperado y merma objetivo.
* **Listas de precios** por canal/sucursal, vigencias y monedas.

## 1.3 Inventario, compras y lotes

* Múltiples **almacenes/sucursales**; inventario por **producto/almacén/lote**.
* **Lotes** con **fecha de caducidad**, trazabilidad y alertas de vencimiento.
* **Órdenes de compra**, recepción (**goods receipt**) con costos y asignación de lotes.
* Ajustes de inventario y **transferencias** entre almacenes (opcional GRE si traslado).

## 1.4 Producción (panificación)

* **Órdenes de producción** por receta (planificada vs real).
* **Consumo de insumos** (descarga de stock) y **producción de terminados** (ingreso a stock/lote).
* Registro de **mermas reales** y rendimiento; recalculo de costo estándar.

## 1.5 Ventas / POS / Pagos

* **POS** con búsqueda rápida, lector código/QR opcional, descuentos, **cierres de caja**.
* Medios de pago: **efectivo, tarjeta, Yape/Plin, transferencia** con **conciliación**.
* Emisión de **CPE** (boleta/factura/notas) vía **SEE** o **PSE (Nubefact)**; descarga de PDF/XML/CDR.
* **GRE** para traslados (tienda–planta, etc.).

## 1.6 Reportes y auditoría

* **Kardex** por producto/almacén/lote; **stock al día**; **ventas por hora/canal**; **mermas**.
* **Cierres de caja** y conciliaciones (pagos externos).
* **Bitácora/Audit log** por usuario/acción/entidad.

## 1.7 Configuraciones

* Impuestos (IGV/tasas/exoneraciones por período), series y numeración CPE/GRE por tenant.
* Integraciones: **pasarelas de pago** (Izipay/Culqi/Niubiz), **PSE**.
* Plantillas de impresión, monedas, formatos de fecha, zona horaria.

---

# 2) Requisitos no funcionales

* **Seguridad & aislamiento**: **RLS** por `tenant_id` en todas las tablas de negocio; JWT con `tenant_id` en claims. (RLS nativa de Postgres; Supabase soporta policies con JWT). ([PostgreSQL][1], [Supabase][2])
* **Cumplimiento local**: soporte **CPE** (SEE/PSE) y **GRE**; parametrización tributaria (IGV, exoneraciones por vigencia) y conservación de comprobantes. ([NubeFact][3], [Gobierno del Perú][4])
* **Disponibilidad**: tolerante a fallos por zona; rollbacks de despliegue; backups automáticos de DB con restauración probada.
* **Rendimiento**: p95 < 300 ms en endpoints críticos (POS, stock); lectura de catálogo < 100 ms con cache.
* **Escalabilidad**: horizontal en servicios stateless; índices por `(tenant_id, ...)`; paginación; límites por plan.
* **Observabilidad**: trazas distribuidas, métricas (RPS/latencia/error rate), logs estructurados, auditoría a nivel dominio.
* **Mantenibilidad**: arquitectura **hexagonal**; contratos API versionados; pruebas multi-capa (unidad/integ/e2e).
* **Usabilidad**: POS “rápido con teclado” y modo degradado si hay microcortes (cola local y reintentos).
* **Internacionalización**: `es-PE`, PEN, decimales latam, formatos de fecha 24h.

---

# 3) Suposiciones y restricciones

* MVP **sin colas/mensajería**: todo síncrono (REST); tareas programadas con `APScheduler` y operaciones idempotentes.
* **DB compartida + RLS** como modelo multi-tenant de arranque (migrable a “schema por tenant” o “DB por tenant” más adelante).
* Hosting: Front **Next.js (Vercel)**; servicios **FastAPI**; **PostgreSQL/Supabase**; almacenamiento S3-compatible.

---

# 4) Roles y permisos (matriz base)

| Recurso/Acción       | OWNER | MANAGER |      CASHIER |        BAKER |  STOREKEEPER |
| -------------------- | ----: | ------: | -----------: | -----------: | -----------: |
| Tenants/Planes       |     ✔ |       – |            – |            – |            – |
| Usuarios/Roles       |     ✔ |       ✔ |            – |            – |            – |
| Catálogo/Precios     |     ✔ |       ✔ |        (ver) |            – |        (ver) |
| Recetas              |     ✔ |       ✔ |            – |            ✔ |            – |
| Inventario (ajustes) |     ✔ |       ✔ |            – |            – |            ✔ |
| Compras/Recepciones  |     ✔ |       ✔ |            – |            – |            ✔ |
| Producción           |     ✔ |       ✔ |            – |            ✔ |            ✔ |
| POS/Ventas           |     ✔ |       ✔ |            ✔ |            – |            – |
| CPE/GRE              |     ✔ |       ✔ | (emitir CPE) |            – | (emitir GRE) |
| Reportes             |     ✔ |       ✔ |     (ventas) | (producción) |      (stock) |

> La autorización se hace **RBAC** + políticas RLS por fila.

---

# 5) Modelo de datos (ERD Mermaid)

```mermaid
erDiagram
    TENANT ||--o{ TENANT_DOMAIN : has
    TENANT ||--o{ USER_MEMBERSHIP : includes
    USER ||--o{ USER_MEMBERSHIP : joins

    TENANT {
      uuid id PK
      text name
      text plan
      text status
      timestamptz created_at
    }
    TENANT_DOMAIN {
      uuid id PK
      uuid tenant_id FK
      text domain
      bool is_primary
    }
    USER {
      uuid id PK
      text email
      text name
      text status
    }
    USER_MEMBERSHIP {
      uuid id PK
      uuid tenant_id FK
      uuid user_id FK
      text role
    }

    CATEGORY ||--o{ PRODUCT : groups
    TENANT ||--o{ CATEGORY : owns
    TENANT ||--o{ PRODUCT : owns
    PRODUCT ||--o{ RECIPE : has
    RECIPE ||--o{ RECIPE_ITEM : composed_of

    CATEGORY {
      uuid id PK
      uuid tenant_id FK
      text name
    }
    PRODUCT {
      uuid id PK
      uuid tenant_id FK
      text sku
      text name
      text type
      text unit
      text tax_code
      bool active
      bool is_batch_tracked
      int shelf_life_days
    }
    RECIPE {
      uuid id PK
      uuid tenant_id FK
      uuid product_id FK
      numeric yield_qty
      text yield_unit
      numeric loss_pct
    }
    RECIPE_ITEM {
      uuid id PK
      uuid tenant_id FK
      uuid recipe_id FK
      uuid ingredient_id FK
      numeric qty
      text unit
      numeric baker_pct
    }

    TENANT ||--o{ WAREHOUSE : has
    PRODUCT ||--o{ STOCK_LEVEL : tracked_in
    PRODUCT ||--o{ STOCK_LOT : batches
    WAREHOUSE ||--o{ STOCK_LEVEL : holds
    WAREHOUSE ||--o{ STOCK_MOVEMENT : records
    STOCK_LOT ||--o{ STOCK_MOVEMENT : referenced_by

    WAREHOUSE {
      uuid id PK
      uuid tenant_id FK
      text name
      text address
      text branch_code
    }
    STOCK_LEVEL {
      uuid id PK
      uuid tenant_id FK
      uuid product_id FK
      uuid warehouse_id FK
      numeric qty_on_hand
      numeric qty_reserved
    }
    STOCK_LOT {
      uuid id PK
      uuid tenant_id FK
      uuid product_id FK
      text lot_code
      date exp_date
      timestamptz created_at
    }
    STOCK_MOVEMENT {
      uuid id PK
      uuid tenant_id FK
      timestamptz ts
      uuid product_id FK
      uuid warehouse_id FK
      uuid lot_id
      numeric qty
      text uom
      text type
      text ref_type
      uuid ref_id
      text note
    }

    SUPPLIER ||--o{ PURCHASE_ORDER : placed
    PURCHASE_ORDER ||--o{ PURCHASE_ITEM : has
    PURCHASE_ORDER ||--o{ GOODS_RECEIPT : results_in
    GOODS_RECEIPT ||--o{ GOODS_RECEIPT_ITEM : contains

    SUPPLIER {
      uuid id PK
      uuid tenant_id FK
      text ruc
      text name
      text contact
      text email
      text phone
    }
    PURCHASE_ORDER {
      uuid id PK
      uuid tenant_id FK
      uuid supplier_id FK
      text status
      timestamptz eta
      numeric total
      text currency
    }
    PURCHASE_ITEM {
      uuid id PK
      uuid tenant_id FK
      uuid purchase_id FK
      uuid product_id FK
      numeric qty
      text unit
      numeric unit_cost
      numeric tax_rate
    }
    GOODS_RECEIPT {
      uuid id PK
      uuid tenant_id FK
      uuid purchase_id FK
      timestamptz received_at
      text doc_ref
    }
    GOODS_RECEIPT_ITEM {
      uuid id PK
      uuid tenant_id FK
      uuid receipt_id FK
      uuid product_id FK
      uuid lot_id FK
      uuid warehouse_id FK
      numeric qty
      text unit
      numeric unit_cost
    }

    POS_REGISTER ||--o{ SALE : processes
    SALE ||--o{ SALE_ITEM : includes
    SALE ||--o{ PAYMENT : gets
    SALE ||--o{ CPE : issues
    GRE ||--o{ STOCK_MOVEMENT : supports

    POS_REGISTER {
      uuid id PK
      uuid tenant_id FK
      text code
      uuid warehouse_id FK
      bool is_open
      timestamptz opened_at
      uuid opened_by
      timestamptz closed_at
      uuid closed_by
      numeric opening_cash
      numeric closing_cash
    }
    SALE {
      uuid id PK
      uuid tenant_id FK
      timestamptz ts
      uuid pos_register_id FK
      uuid customer_id
      text status
      numeric subtotal
      numeric tax
      numeric total
      text currency
      text payment_status
      uuid cpe_id
    }
    SALE_ITEM {
      uuid id PK
      uuid tenant_id FK
      uuid sale_id FK
      uuid product_id FK
      numeric qty
      text unit
      numeric unit_price
      numeric discount_pct
      numeric tax_rate
    }
    PAYMENT {
      uuid id PK
      uuid tenant_id FK
      uuid sale_id FK
      text method
      numeric amount
      text external_txn_id
      text status
      jsonb payload_json
    }
    CPE {
      uuid id PK
      uuid tenant_id FK
      %% FACTURA|BOLETA|NC|ND
      text type
      text series
      text number
      timestamptz issue_ts
      text status
      %% SEE|NUBEFACT|OTRO
      text provider
      text provider_ref
      text pdf_url
      text xml_url
      text cdr_url
      text sunat_ticket
      jsonb response_json
    }
    GRE {
      uuid id PK
      uuid tenant_id FK
      text series
      text number
      timestamptz issue_ts
      text status
      jsonb json_payload
      text sunat_ticket
    }
```

---

# 6) Diagramas de arquitectura (Mermaid)

## 6.1 Sistema (contexto, “C4-ish”)

```mermaid
flowchart LR
  actor(Cliente)
  subgraph Browser [Navegador del cliente]
    UI[Next.js App]
  end

  subgraph SaaS [SaaS Panaderías]
    BFF[Gateway / BFF]
    subgraph SVCs [Microservicios FastAPI]
      IDT[identity-tenants]
      CAT[catalog-recipes]
      INV[inventory-procurement]
      POS[sales-pos-fiscal]
    end
    DB[(PostgreSQL/Supabase)]
    OBJ[(Storage S3)]
  end

  subgraph Ext [Servicios externos]
    PAY[Pasarelas: Izipay/Culqi/Niubiz]
    CPE["CPE: SEE / PSE (Nubefact)"]
    SUNAT["SUNAT (validación CPE/GRE)"]
  end

  Cliente-- Usa -->UI
  UI-- REST/JWT -->BFF
  BFF-- REST -->IDT & CAT & INV & POS
  BFF-- set app.tenant_id -->DB
  SVCs-- R/W -->DB
  SVCs-- Presigned URLs -->OBJ
  POS-- Emite -->CPE-- Intercambia -->SUNAT
  UI-- SDK -->PAY
  PAY-- Webhook -->POS
```

## 6.2 Contenedores (detalle técnico)

```mermaid
flowchart TD
  subgraph Frontend [Frontend - Vercel]
    NJS[Next.js App Router\nNextAuth/Supabase Auth]
  end

  subgraph Backend [Kubernetes/ECS]
    GW["Gateway API (FastAPI)\nSubdominio→tenant_id"]
    IDT[identity-tenants]
    CAT[catalog-recipes]
    INV[inventory-procurement]
    POS[sales-pos-fiscal]
  end

  DB[(PostgreSQL 16 / Supabase)]
  S3[(S3-compatible)]
  PAY[Izipay/Culqi/Niubiz]
  NUBE["Nubefact (PSE) / SEE"]
  SUNAT[SUNAT]

  NJS-->GW
  GW-->IDT
  GW-->CAT
  GW-->INV
  GW-->POS
  IDT & CAT & INV & POS --> DB
  CAT & INV & POS --> S3
  NJS-->PAY
  PAY--webhook-->POS
  POS<-->NUBE
  NUBE<-->SUNAT
```

---

# 7) Diagramas de **secuencia** (flujos críticos)

## 7.1 Venta POS con pago Yape y CPE

```mermaid
sequenceDiagram
  participant U as Cajero (POS)
  participant UI as Next.js POS
  participant GW as Gateway API
  participant POSsvc as sales-pos-fiscal
  participant INV as inventory
  participant PAY as Pasarela (Izipay/Culqi/Niubiz)
  participant CPE as CPE (SEE/Nubefact)

  U->>UI: Selecciona ítems / cobra
  UI->>GW: POST /sales (JWT c/tenant_id)
  GW->>POSsvc: Crea venta (PENDING) + reserva stock
  POSsvc->>INV: POST /stock/reserve (items)
  INV-->>POSsvc: OK (reservado)

  UI->>PAY: SDK tokeniza/cobra Yape
  PAY-->>POSsvc: Webhook: pago PAID (firma válida)

  POSsvc->>CPE: POST /cpe (json)
  CPE-->>POSsvc: PDF/XML/CDR + status
  POSsvc->>INV: POST /stock/commit (rebaja real)
  POSsvc-->>GW: Venta CONFIRMED + links CPE
  GW-->>UI: Ticket + enlace CPE
```

*(Las pasarelas en Perú exponen SDKs + **webhooks**/notificaciones para confirmar pagos). ([developers.izipay.pe][5], [testdevelopers.izipay.pe][6], [docs.culqi.com][7], [niubiz.com.pe][8])*

## 7.2 Orden de producción

```mermaid
sequenceDiagram
  participant B as Maestro Panadero
  participant UI as App Producción
  participant GW as Gateway
  participant CAT as catalog-recipes
  participant INV as inventory
  participant PR as production (en INV)

  B->>UI: Define OP (producto terminado, cantidad)
  UI->>GW: POST /production-orders
  GW->>CAT: GET receta + insumos escalados
  GW->>PR: Crear OP (PLANNED)
  PR->>INV: POST /stock/consume (insumos por lote)
  INV-->>PR: Movimientos CONSUME
  PR->>INV: POST /stock/produce (terminados a lote)
  INV-->>PR: Movimientos PRODUCTION_IN
  PR-->>GW: OP FINISHED (rendimiento/merma real)
  GW-->>UI: OP cerrada + stock actualizado
```

## 7.3 Recepción de compra con lotes

```mermaid
sequenceDiagram
  participant S as Storekeeper
  participant UI as App Compras
  participant GW as Gateway
  participant INV as inventory

  S->>UI: Registrar GR (proveedor, productos)
  UI->>GW: POST /goods-receipts
  GW->>INV: Crear GR + ítems
  INV->>INV: Crear lotes (exp_date) + stock_level
  INV-->>GW: Kardex y saldos actualizados
  GW-->>UI: GR ok + etiquetas de lote
```

---

# 8) Diagramas de **estado**

## 8.1 `production_order`

```mermaid
stateDiagram-v2
  [*] --> PLANNED
  PLANNED --> IN_PROGRESS: start()
  IN_PROGRESS --> PAUSED: pause()
  PAUSED --> IN_PROGRESS: resume()
  IN_PROGRESS --> FINISHED: complete(rendimiento, merma)
  IN_PROGRESS --> CANCELLED: cancel(motivo)
  PLANNED --> CANCELLED: cancel()
  FINISHED --> [*]
  CANCELLED --> [*]
```

## 8.2 `pos_register` (caja)

```mermaid
stateDiagram-v2
  [*] --> CLOSED
  CLOSED --> OPEN: open(opening_cash, user)
  OPEN --> OPEN: movements(cash_in/out)
  OPEN --> CLOSED: close(closing_cash, arqueo)
  CLOSED --> [*]
```

---

# 9) RLS multi-tenant (políticas ejemplo)

* **Idea**: todas las tablas llevan `tenant_id`; cada request establece `SET app.tenant_id` y las políticas **USING/WITH CHECK** hacen cumplir el aislamiento. (RLS nativa de Postgres; `CREATE POLICY` y `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`). ([PostgreSQL][1])

```sql
ALTER TABLE product ENABLE ROW LEVEL SECURITY;

CREATE POLICY product_by_tenant ON product
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

* En **Supabase**, puedes mapear `jwt.claims.tenant_id` en las policies. ([Supabase][2])

---

# 10) API (contratos REST clave)

* `POST /tenants` (admin): crea tenant y dominio; `GET /me`.
* `POST /products`, `GET /products?search=...`, `POST /recipes`, `POST /price-lists`.
* `POST /warehouses`, `POST /stock/adjust`, `POST /purchase-orders`, `POST /goods-receipts`.
* `POST /production-orders`, `POST /stock/consume|produce`.
* `POST /pos/register/open|close`, `POST /sales`, `POST /payments`, `POST /sales/commit`.
* `POST /fiscal/cpe`, `POST /fiscal/gre`.
* `POST /payments/webhook` (firma/verificación según pasarela). *(Izipay/Culqi/Niubiz proveen notificaciones/webhooks/SDKs).* ([developers.izipay.pe][5], [docs.culqi.com][7], [niubiz.com.pe][8])

---

# 11) Calidad, pruebas y observabilidad

* **Pruebas**:

  * Unidad (dominio hexagonal: recetas, reservas, reglas de stock).
  * Integración (repos/DB con RLS activa; prueba de fuga entre tenants debe fallar).
  * E2E (POS → cobro → CPE/GRE). Webhooks simulados.
* **Observabilidad**:

  * Métricas: `http_server_requests_seconds_*`, errores por endpoint/tenant, latencias, colas locales POS.
  * Trazas: `X-Tenant` como atributo; spans por interacción externa (PSE/pagos).
  * Logs JSON con `tenant_id`, `user_id`, `ip`, `action`.

---

# 12) Integraciones locales (referencias breves)

* **CPE/PSE**: **Nubefact** (API REST para enviar JSON/TXT y recibir PDF/XML/CDR). ([NubeFact][3])
* **GRE**: emisión por **SEE-SOL** (RUC + Clave SOL y requisitos). ([Gobierno del Perú][4])
* **Pagos**:

  * **Izipay**: SDK web y **webhooks** de notificación. ([testdevelopers.izipay.pe][6], [developers.izipay.pe][5])
  * **Culqi**: pagos online + **Yape** vía API/Checkout. ([docs.culqi.com][7])
  * **Niubiz**: soluciones e integración con botón **Yape**. ([niubiz.com.pe][9])

---

# 13) Cómo escribir diagramas **Mermaid** (guía rápida)

* Encierra el diagrama en un bloque de código:
  \`\`\`mermaid
  flowchart TD
  A --> B
  \`\`\`
* Tipos usados aquí: **flowchart**, **sequenceDiagram**, **stateDiagram-v2**, **erDiagram**.
* Referencia oficial de sintaxis y ejemplos: **Mermaid docs** (diagramas, estado, etc.). ([mermaid.js.org][10], [docs.mermaidchart.com][11])

---

## 14) Checklist de ingeniería para construir el MVP (sin tiempos)

1. **Tenancy + Auth**: subdominio→`tenant_id`, JWT con `tenant_id`, RLS activo y testeado.
2. **Catálogo & Recetas**: editor de recetas (porcentaje panadero), listas de precio.
3. **Inventario con lotes**: stock\_level + stock\_movement + Kardex.
4. **Producción**: OP → consume/produce → merma → costos.
5. **POS + Pagos**: flujo reserva/commit/release, SDK pago + webhook.
6. **Fiscal**: adapter **PSE (Nubefact)** primero; luego **SEE** si lo piden.
7. **Reportes y cierres**: ventas por hora, mermas, cierres de caja, exportables.
8. **Observabilidad & Auditoría**: métricas/trazas/logs, audit log de dominio.


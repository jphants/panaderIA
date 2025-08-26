# Backend de PanaderIA

¡Vamos a armar tu MVP como si mañana tuvieras que abrir 20 panaderías en producción! Tomé tu plan base y lo ajusté a lo que pediste (Python + Next.js + PostgreSQL/Supabase + Vercel, **sin** colas, ni eventos/mensajería), añadiendo el flujo real de una panadería en Perú y un “bench” de software referente local para orientar decisiones.

# 0) Qué hace distinto a un ERP para panaderías (Perú)

**Flujo operativo típico** (resumen aterrizado a Perú):

1. **Abastecimiento**: compras de harina, levadura, azúcar, grasas, sal, mejoradores → recepción con lotes y **vida útil**, mermas, y **GRE** si hay traslados entre locales. ([Comprobantes de Pago Electrónicos][1])
2. **Producción (panificación)**: recetas (porcentaje panadero), cálculo de rendimientos, programación de hornadas (amasado → primera fermentación → dividido/boleado → formado → fermentación final → horneado), control de **mermas** y “sobras” de mostrador. ([Tesis USAT][2], [Repositorio ULima][3])
3. **Exhibición/venta**: POS rápido, múltiples medios de pago (efectivo, tarjetas, **Yape/Plin**), cierres de caja y arqueos. SUNAT fiscaliza el uso de billeteras digitales en comercios; conviene conciliación diaria. ([infobae][4])
4. **Cumplimiento**: **boleta/factura electrónica (CPE)** y **Guía de Remisión Electrónica** cuando corresponde. (CPE por SEE‐del Contribuyente o vía PSE). ([Comprobantes de Pago Electrónicos][5])
5. **Inocuidad/BPM**: registros y controles acorde a la **Norma Sanitaria de panaderías** (MINSA). Tu ERP debe permitir checklists y evidencias. ([Digesa][6], [www.slideshare.net][7])

**Referentes locales** (para mirar funcionalidades y UX):

* **Alegra POS**: POS + CPE con requisitos SUNAT. ([Alegra][8])
* **Bsale**: POS con **boleta/factura electrónica** + inventario en tiempo real (opera en Perú). ([Bsale][9])
* **Panadex 2.0**: vertical para panaderías (módulos de compras, producción, inventarios, ventas). ([panaderiaypasteleriaperuana.com][10])
* **Nubefact**: PSE con **API** para emitir CPE desde tu sistema. (Úsalo como “adaptador” de facturación). ([nubefact.com][11])
* **Pasarelas de pago** locales con API: **Izipay**, **Culqi** y **Niubiz** (incluye Yape por partners). ([developers.izipay.pe][12], [docs.culqi.com][13], [niubiz.com.pe][14])

> Nota tributaria: ciertas operaciones de alimentos en los **Apéndices I y II** de la Ley del IGV mantienen exoneraciones vigentes hasta el **31-12-2025** (parametriza **tasas por producto y período**; no “duro-codifiques” IGV). ([SUNAT][15], [LP][16])

---

# 1) Arquitectura de alto nivel (MVP, sin colas/eventos)

**Front**: **Next.js (App Router) en Vercel**, multi-tenant por subdominio (`{tenant}.tusaaS.com`), **NextAuth (OIDC)** o **Supabase Auth**.
**Back**: 5 microservicios **FastAPI** (Python 3.12), **REST** síncrono con JWT (propaga `tenant_id` y `role`).
**Datos**: **PostgreSQL 16 (o Supabase)**, **un solo esquema compartido + RLS por `tenant_id`**.
**Archivos**: S3-compatible con **pre-signed URLs** (fotos de productos, plantillas CPE, etc.).
**Pagos**: SDK web (Izipay/Culqi/Niubiz) directo desde Next.js + confirmación en backend. ([developers.izipay.pe][17], [docs.culqi.com][13])

**Microservicios mínimos**

1. **gateway-api** (BFF):

   * Middleware de subdominio→`tenant_id`.
   * Verifica JWT/roles y **inyecta `tenant_id`** en cada request al resto.
2. **identity-tenants**:

   * Tenants (planes, dominios, branding), usuarios, roles (dueño, gerente, cajero, maestro panadero, almacenista), invitaciones.
   * Provisiona credenciales y **seed** inicial.
3. **catalog-recipes**:

   * Productos, categorías, **recetas por porcentaje panadero**, costos estándares, listas de precios, impuestos.
   * Escalado de receta por hornada (rendimientos/mermas objetivo).
4. **inventory-procurement**:

   * Almacenes/sucursales, **lotes** y **vida útil**, stock, órdenes de compra, ingresos, ajustes y **movimientos** (incluye “reservar/confirmar/liberar stock” para ventas y producción).
   * **Órdenes de producción** y **consumo de insumos** por receta/batch; mermas reales.
5. **sales-pos-fiscal**:

   * POS (tickets), ventas, cierres de caja, pagos (tarjeta/efectivo/Yape/Plin), vales;
   * Integración **CPE** (boleta/factura/notas) vía **SEE del Contribuyente** o **PSE (Nubefact)**; **GRE** cuando haya traslados. ([Comprobantes de Pago Electrónicos][5], [nubefact.com][11])

> Sin mensajería: las orquestaciones se resuelven con **transacciones DB** y **REST idempotente**. Para tareas programadas (e.g., cierre automático), usa **APScheduler** en cada servicio (cron) y un flag `last_run_at` para evitar duplicidad.

**Interacciones clave (síncronas)**

* **POS → inventario**: `POST /stock/reserve` → `POST /sales/commit` (confirmar y rebajar) → `POST /stock/release` (si falla).
* **Producción**: `POST /production-orders` (calcula consumo por receta) → `POST /stock/consume` insumos → `POST /stock/produce` productos terminados.
* **CPE**: `POST /fiscal/cpe` (envía JSON al proveedor elegido, guarda `cpe_status`, `sunat_ticket`, URLs PDF/XML/CDR). ([nubefact.com][11])
* **Pagos**: Front integra SDK (tokeniza) → backend valida firma/`transactionId` (webhook) y concilia con la venta. ([testdevelopers.izipay.pe][18])

---

# 2) Multi-tenancy + RLS (patrón recomendado)

**Patrón**: DB compartida + esquema compartido + **RLS por `tenant_id`**.

* Todas las tablas de negocio llevan `tenant_id UUID NOT NULL`.
* Política RLS: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
* El gateway establece `SET app.tenant_id = '<uuid>'` por conexión (o, en Supabase, usa `jwt.claims.tenant_id` en las policies).
* Catálogo `tenants` y `domains` para resolver subdominios.

> Este enfoque reduce costo/operación y te da aislamiento lógico robusto desde el día 1; es la práctica recomendada para SaaS early-stage. (La RLS de Postgres es nativa). ([Digesa][6])

**Ejemplo de policy (PostgreSQL)**

```sql
ALTER TABLE product ENABLE ROW LEVEL SECURITY;
CREATE POLICY by_tenant ON product
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

# 3) Modelo de datos (núcleo del MVP)

**Identidad / Tenancy**

* `tenant(id, name, plan, status, created_at, ... )`
* `tenant_domain(id, tenant_id, domain, is_primary)`
* `user(id, email, name, status, ... )`
* `user_membership(id, tenant_id, user_id, role)` — roles: `OWNER|MANAGER|CASHIER|BAKER|STOREKEEPER`

**Catálogo & Recetas**

* `category(id, tenant_id, name)`
* `product(id, tenant_id, sku, name, type, tax_code, price_list_id, unit, is_batch_tracked, shelf_life_days, active)`

  * `type = 'FINISHED'|'INGREDIENT'|'PACKAGE'`
* `recipe(id, tenant_id, product_id, yield_qty, yield_unit, loss_pct, notes)`
* `recipe_item(id, tenant_id, recipe_id, ingredient_id, qty, unit, baker_pct)`
* `price_list(id, tenant_id, name, currency)`
* `price_list_item(id, tenant_id, price_list_id, product_id, price, valid_from, valid_to)`

**Inventario & Compras**

* `warehouse(id, tenant_id, name, address, branch_code)`
* `stock_lot(id, tenant_id, product_id, lot_code, exp_date, created_at)`
* `stock_level(id, tenant_id, product_id, warehouse_id, qty_on_hand, qty_reserved)`
* `stock_movement(id, tenant_id, ts, product_id, warehouse_id, lot_id, qty, uom, type, ref_type, ref_id, note)`

  * `type = 'PURCHASE'|'PRODUCTION_IN'|'CONSUME'|'SALE'|'ADJUST'|'TRANSFER'`
* `supplier(id, tenant_id, ruc, name, contact, phone, email)`
* `purchase_order(id, tenant_id, supplier_id, status, eta, total, currency)`
* `purchase_item(id, tenant_id, purchase_id, product_id, qty, unit, unit_cost, tax_rate)`
* `goods_receipt(id, tenant_id, purchase_id, received_at, doc_ref)`
* `goods_receipt_item(id, tenant_id, receipt_id, product_id, lot_id, warehouse_id, qty, unit, unit_cost)`

**Producción**

* `production_order(id, tenant_id, product_id, planned_qty, unit, status, scheduled_at, started_at, finished_at, yield_real, loss_real_pct)`
* `production_consume(id, tenant_id, order_id, ingredient_id, qty, unit)`
* `production_output(id, tenant_id, order_id, product_id, lot_id, warehouse_id, qty, unit)`

**Ventas, POS, Pagos**

* `pos_register(id, tenant_id, code, warehouse_id, is_open, opened_at, opened_by, closed_at, closed_by, opening_cash, closing_cash)`
* `sale(id, tenant_id, ts, pos_register_id, customer_id, status, subtotal, tax, total, currency, payment_status, cpe_id)`
* `sale_item(id, tenant_id, sale_id, product_id, qty, unit, unit_price, discount_pct, tax_rate)`
* `payment(id, tenant_id, sale_id, method, amount, external_txn_id, status, payload_json)`

  * `method = 'CASH'|'CARD'|'YAPE'|'PLIN'|'TRANSFER'`
* `cash_movement(id, tenant_id, pos_register_id, ts, type, amount, note)`
* `customer(id, tenant_id, doc_type, doc_number, name, email, phone)`

**Fiscal (SUNAT)**

* `cpe(id, tenant_id, type, series, number, issue_ts, status, provider, provider_ref, pdf_url, xml_url, cdr_url, sunat_ticket, response_json)`

  * `type = 'FACTURA'|'BOLETA'|'NC'|'ND'`
  * `provider = 'SEE'|'NUBEFACT'|'OTRO'` (adapter)
* `gre(id, tenant_id, series, number, issue_ts, status, json_payload, sunat_ticket)`

**Config & auditoría**

* `tax_config(id, tenant_id, code, name, rate, valid_from, valid_to)`
* `integration_setting(id, tenant_id, provider, key, secret, extra_json)`
* `audit_log(id, tenant_id, ts, user_id, action, entity, entity_id, data_json)`

**Índices recomendados**

* `idx_{table}_tenant` en todas.
* Compuestos según uso: `stock_level(tenant_id, warehouse_id, product_id)`, `price_list_item(tenant_id, product_id, valid_from DESC)`, `stock_movement(tenant_id, product_id, ts DESC)`.

---

# 4) Casos de uso críticos (cómo se encadenan, sin colas)

**A) Venta en mostrador con CPE y pago Yape**

1. POS crea `sale` (status=`PENDING`) → `inventory/reserve` (por cada item).
2. Pasarela (Izipay/Culqi/Niubiz) **tokeniza** y cobra → webhook confirma (`payment.status=PAID`). ([developers.izipay.pe][12], [docs.culqi.com][13])
3. `sales/commit`: genera CPE vía `fiscal/cpe` (adapter a SEE/PSE) y **rebaja stock** (movimiento `SALE`). ([Comprobantes de Pago Electrónicos][5], [nubefact.com][11])
4. Si falla el cobro o CPE → `inventory/release` y `sale.status=CANCELLED`.
5. Cierre de caja → `pos_register.close` (cuadra con `payment` + `cash_movement`).

**B) Orden de producción pan francés**

1. Panadero genera `production_order` (ej. 50 kg masa) con receta y rendimientos.
2. `inventory/consume` descuenta insumos por receta (mov. `CONSUME`).
3. `inventory/produce` ingresa terminados a lote con **vida útil** (mov. `PRODUCTION_IN`).
4. Registrar **mermas reales** y **rendimiento**; ajusta costo estándar.

**C) Recepción de compras**

1. `purchase_order` → `goods_receipt` (asigna lotes/fechas) → actualiza `stock_level`.
2. Si hay traslado entre locales, emite **GRE**. ([Comprobantes de Pago Electrónicos][1])

---

# 5) Integraciones locales (SUNAT y pagos) — enfoque MVP

**CPE (SUNAT)**

* Opción 1: **SEE – del Contribuyente** (tú firmas y envías). Requiere Clave SOL y alta como emisor electrónico. ([Comprobantes de Pago Electrónicos][5])
* Opción 2: **PSE (Nubefact)**: tu servicio envía JSON y recibe PDF/XML/CDR; simplifica operación. (Recomendado para MVP). ([nubefact.com][11])

**GRE (SUNAT)**

* Implementa emisión desde móvil/PC para traslados (p. ej., planta → tienda). ([Comprobantes de Pago Electrónicos][1])

**Pagos**

* **Izipay** (SDK web + REST; tokens, notificaciones con `transactionId`). ([developers.izipay.pe][17], [testdevelopers.izipay.pe][18])
* **Culqi** (botón/Checkout + API; soporta **Yape** como medio). ([docs.culqi.com][13])
* **Niubiz** (botón/QR/Yape por partners). ([niubiz.com.pe][14], [niubiz.com.pe][19])

---

# 6) Frontend (Next.js + Vercel) — multi-tenant por subdominio

* **Middleware** lee `host` → resuelve `tenant_id` (cache 5 min).
* **NextAuth** o **Supabase Auth** con “organizations”/`tenant_id` en el **JWT**.
* **Rutas**:

  * `/admin` (tú): creación de panaderías (tenants), branding, dominio.
  * `/app` (cliente): POS, producción, inventario, compras, reportes.
* **POS** offline-light: cache de catálogo/recetas y **“cola local”** de ventas reintentables (aún sin broker global).

---

# 7) Plan mínimo por microservicio (qué construir primero)

**identity-tenants**

* Endpoints: `POST /tenants` (provisionar), `POST /users/invite`, `GET /me`, `GET /roles`.
* Reglas: un `owner` por tenant; RBAC server-side; seed de tasas/impuestos.
* Pruebas: RLS estricta; cruce entre tenants debe fallar.

**catalog-recipes**

* `POST /products`, `GET /products?search`, `POST /recipes`, `POST /price-lists`.
* Lógica: cálculo de costo objetivo por receta (con `loss_pct`).
* UI: editor de receta (porcentajes + escalado).

**inventory-procurement**

* `POST /warehouses`, `POST /stock/adjust`, `POST /purchase-orders`, `POST /goods-receipts`, `POST /stock/reserve|release|consume|produce`.
* Reglas: **idempotencia** por `idempotency_key`; saldos no negativos.
* Reportes: Kardex por producto/almacén.

**sales-pos-fiscal**

* `POST /pos/register/open|close`, `POST /sales`, `POST /payments`, `POST /sales/commit`.
* Integración CPE (proveedor abstraído): `POST /fiscal/cpe` con “driver” (`SEE`|`NUBEFACT`).
* Webhook pagos: valida firma y concilia.

**gateway-api**

* Middleware subdominio→`tenant_id`; verificación JWT; **SET `app.tenant_id`** antes de cada query.
* Rate-limit básico por tenant.

---

# 8) Esquema SQL (extractos clave)

```sql
-- Tenancy
CREATE TABLE tenant(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  plan text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenant_domain(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  domain text NOT NULL,
  is_primary boolean NOT NULL DEFAULT false,
  UNIQUE(domain)
);

-- Productos
CREATE TABLE product(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  sku text UNIQUE,
  name text NOT NULL,
  type text NOT NULL CHECK (type IN ('FINISHED','INGREDIENT','PACKAGE')),
  unit text NOT NULL,
  tax_code text,
  is_batch_tracked boolean NOT NULL DEFAULT false,
  shelf_life_days int,
  active boolean NOT NULL DEFAULT true
);

-- Recetas
CREATE TABLE recipe(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  product_id uuid NOT NULL REFERENCES product(id),
  yield_qty numeric(18,4) NOT NULL,
  yield_unit text NOT NULL,
  loss_pct numeric(5,2) NOT NULL DEFAULT 0
);

CREATE TABLE recipe_item(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  recipe_id uuid NOT NULL REFERENCES recipe(id),
  ingredient_id uuid NOT NULL REFERENCES product(id),
  qty numeric(18,4) NOT NULL,
  unit text NOT NULL,
  baker_pct numeric(8,4)
);

-- Inventario (lotes + saldos + movimientos)
CREATE TABLE stock_lot(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  product_id uuid NOT NULL REFERENCES product(id),
  lot_code text NOT NULL,
  exp_date date,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stock_level(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  product_id uuid NOT NULL REFERENCES product(id),
  warehouse_id uuid NOT NULL,
  qty_on_hand numeric(18,4) NOT NULL DEFAULT 0,
  qty_reserved numeric(18,4) NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, product_id, warehouse_id)
);

CREATE TABLE stock_movement(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  product_id uuid NOT NULL REFERENCES product(id),
  warehouse_id uuid NOT NULL,
  lot_id uuid,
  qty numeric(18,4) NOT NULL,
  uom text NOT NULL,
  type text NOT NULL,
  ref_type text,
  ref_id uuid,
  note text
);
```

*(Sigue con `purchase_*`, `production_*`, `sale`, `sale_item`, `payment`, `cpe`, `gre` y `cash_movement` según el catálogo anterior.)*

---

# 9) Seguridad, cumplimiento y Perú-ready (MVP)

* **RLS** obligatoria (tests de cruce de tenants).
* **CPE** y **GRE** parametrizados por tenant (serie, numeración, emisor, modo SEE/PSE). ([Comprobantes de Pago Electrónicos][5])
* **BPM/Inocuidad**: listas de chequeo y evidencias para auditoría municipal/DIGESA. ([Digesa][6])
* **IGV** configurable por producto y período (exoneraciones Apéndices I/II hasta 31-12-2025). ([LP][16])

---

# 10) “Crear panaderías” (tu panel de admin)

1. **Alta de tenant** → subdominio (`acme.tu-saas.com`), branding y plan.
2. **Seed**: roles base, lista inicial de impuestos, plantillas de productos comunes (pan francés, integral, masa hojaldre, etc.).
3. **Usuarios**: invitas al dueño/gerente (owner).
4. **Onboarding asistido**: crea almacenes/sucursales, POS, lista de precios, pasarela de pagos (pega credenciales), CPE (elige SEE/PSE).
5. **Smoke**: crea venta de prueba + CPE en modo “demo”.

---

## Cierre — qué construir primero (hoja de ruta funcional)

1. **POS + Ventas + Reservas de stock + CPE (vía PSE)**
2. **Catálogo/Recetas + Producción (consume/produce + mermas)**
3. **Compras + Recepción (lotes/vida útil) + Kardex**
4. **Pagos locales (Izipay/Culqi/Niubiz) con conciliación y cierres**
5. **Panel admin para crear panaderías (multitenant E2E)**

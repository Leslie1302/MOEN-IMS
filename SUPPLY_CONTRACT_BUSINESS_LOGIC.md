# Supply Contract Management - Business Logic

## 🏢 Business Model Overview

### Supplier Role
**Suppliers are EXTERNAL third-party companies** who:
1. Procure materials from other manufacturers/distributors
2. Supply materials TO the organization (MOEN)
3. Deliver materials TO organization's warehouses
4. Are NOT part of the organization

### Material Flow
```
External Manufacturers
        ↓
    Suppliers (Third-Party)
        ↓
  Organization Warehouses
        ↓
  Electrification Projects
```

## 📦 Key Concepts

### Warehouse Field in Price Catalog
- **Meaning**: Delivery destination/location
- **NOT**: Source warehouse (suppliers don't get materials from org warehouses)
- **Purpose**: Track which warehouse the supplier will deliver to
- **Optional**: Yes (some suppliers may deliver to any warehouse)

### Supply Contract Process
1. **Supplier Selection**: Choose external supplier
2. **Price Negotiation**: Agree on unit rates and terms
3. **Contract Creation**: Document the agreement
4. **Material Order**: Request materials from supplier
5. **Supplier Procurement**: Supplier sources materials externally
6. **Delivery**: Supplier delivers to specified warehouse
7. **Invoice Processing**: Verify and pay supplier

### Invoice Verification
- Compares **quantity invoiced** vs **quantity received**
- Flags discrepancies for review
- Links to MaterialOrder for traceability
- Tracks payment workflow

## 🔑 Important Fields

### SupplierPriceCatalog
- `warehouse`: **Delivery location** (where supplier will deliver)
- `lead_time_days`: Days for supplier to procure and deliver
- `minimum_order_quantity`: Supplier's MOQ requirement
- `unit_rate`: Price per unit from supplier

### SupplyContract
- Documents agreement with external supplier
- Tracks expected value and actual spend
- Can be one-time, framework, or long-term
- Status workflow: draft → pending → active → completed

### SupplierInvoice
- Submitted by supplier after delivery
- Verified by organization storekeeper
- Approved by management
- Paid after approval
- Tracks discrepancies between invoice and received quantities

## 📊 Use Cases

### 1. Cost Estimation
- Compare prices across multiple suppliers
- Select most cost-effective supplier
- Estimate project material costs
- Budget planning

### 2. Supplier Performance
- Track delivery times (lead time)
- Monitor invoice accuracy (discrepancies)
- Rate suppliers (1-5 scale)
- Maintain supplier history

### 3. Contract Management
- Create formal agreements
- Track contract value
- Monitor contract status
- Link invoices to contracts

### 4. Invoice Processing
- Receive supplier invoice
- Verify against actual deliveries
- Flag discrepancies
- Approve for payment
- Track payment status

## 🚫 Common Misconceptions

### ❌ INCORRECT Understanding:
- Suppliers get materials FROM organization warehouses
- Warehouse field = source location
- Suppliers are internal departments
- Materials flow from warehouses to suppliers

### ✅ CORRECT Understanding:
- Suppliers are external third-party companies
- They source materials from other companies
- They deliver TO organization warehouses
- Warehouse field = delivery destination
- Materials flow from suppliers TO warehouses

## 🔄 Integration with Existing System

### Material Request Flow
1. **Schedule Officer** requests material for project
2. **Storekeeper** checks warehouse inventory
3. If insufficient:
   - Review supplier prices
   - Select supplier
   - Create supply contract (if needed)
   - Order from supplier
4. **Supplier** delivers to warehouse
5. **Storekeeper** receives and updates inventory
6. **Supplier** submits invoice
7. **Management** verifies and approves payment

### Data Relationships
```
Supplier (external company)
  ↓ has many
SupplierPriceCatalog (prices for materials)
  ↓ referenced in
SupplyContract (agreement)
  ↓ has many
SupplyContractItem (line items)
  ↓ fulfilled by
MaterialOrder (from Schedule Officer)
  ↓ generates
SupplierInvoice (from supplier)
  ↓ has many
SupplierInvoiceItem (with qty verification)
```

## 📝 Notes for Future Development

1. **Supplier Portal**: Consider external portal for suppliers to submit quotes/invoices
2. **Auto-Selection**: Algorithm to auto-select best supplier based on price/rating/lead time
3. **Purchase Orders**: Generate POs from contracts
4. **Payment Integration**: Link to accounting system
5. **Supplier KPIs**: Dashboard showing supplier performance metrics
6. **Price History**: Track price trends over time
7. **Bulk Ordering**: Combine multiple material requests into single supplier order

## 🎯 System Benefits

- **Cost Savings**: Compare prices to find best rates
- **Transparency**: Clear audit trail for procurement
- **Accountability**: Track who approved what and when
- **Efficiency**: Streamlined supplier invoice processing
- **Accuracy**: Verify invoices against actual deliveries
- **Planning**: Better project cost estimation
- **Performance**: Monitor and rate supplier reliability

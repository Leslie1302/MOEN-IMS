# Performance Grading Workflow Update

## 🎯 Updated Task Completion Logic

The grading system has been updated to accurately reflect the actual workflow and handoff points between roles.

---

## 📋 Role-by-Role Breakdown

### **1. Schedule Officers** 👨‍💼

**Task Definition:**
- 1 Material Request = 1 Task
- If officer creates 20 requests → 20 tasks

**Task Starts:**
- ✅ When they create the material request

**Task Completes:**
- ✅ When **site receipt is logged** for that order
- This is the final confirmation that materials reached the site

**Efficiency Measured:**
- Days from: **Request Creation** → **Site Receipt Logged**

**Why:**
- Schedule Officers are accountable for the entire supply chain
- They need to track requests from start to finish
- Site receipt confirms successful delivery to intended location

**Database Logic:**
```python
# Total Tasks
requests = MaterialOrder.objects.filter(user=schedule_officer)

# Completed Tasks
completed = requests.filter(site_receipt__isnull=False)

# Efficiency
days = (site_receipt.receipt_date - request.date_requested).days
```

---

### **2. Storekeepers** 📦

**Task Definition:**
- 1 Order to Process = 1 Task
- Same orders as Schedule Officers, but from processing perspective

**Task Starts:**
- ✅ When they receive/are assigned the material order

**Task Completes:**
- ✅ When transport status becomes **"In Transit"**
- This confirms materials processed, loaded, and departed

**Efficiency Measured:**
- Days from: **Request Receipt** → **Transport In Transit**

**Why:**
- Storekeepers' responsibility ends when materials leave the warehouse
- "In Transit" status confirms successful handoff to transporter
- Measures their processing and loading speed

**Database Logic:**
```python
# Total Tasks
orders = MaterialOrder.objects.filter(last_updated_by=storekeeper)

# Completed Tasks
completed = orders.filter(materialtransport__status='In Transit')

# Efficiency
days = (transport.date_assigned - order.date_requested).days
```

---

### **3. Transporters** 🚚

**Task Definition:**
- 1 Transport Assignment = 1 Task
- Independent from material orders (one order might have multiple transports)

**Task Starts:**
- ✅ When they are assigned a transport

**Task Completes:**
- ✅ When status is **"Delivered"** AND **site receipt is logged**
- Both conditions must be met

**Efficiency Measured:**
- Days from: **Transport Assignment** → **Site Receipt Logged**

**Why:**
- Transporters must ensure both delivery AND proper handover
- Site receipt confirms materials reached the site and were accepted
- Measures their delivery reliability and documentation

**Database Logic:**
```python
# Total Tasks
transports = MaterialTransport.objects.filter(transporter_name=transporter.username)

# Completed Tasks
completed = transports.filter(
    status='Delivered',
    site_receipt__isnull=False
)

# Efficiency
days = (receipt.receipt_date - transport.date_assigned).days
```

---

## 🔄 Workflow Visualization

```
┌─────────────────┐
│ SCHEDULE OFFICER│
│  Creates Request│
└────────┬────────┘
         │ Task: Request → Site Receipt
         │ ✓ Complete: Site receipt logged
         │
         v
┌─────────────────┐
│  STOREKEEPER    │
│ Processes Order │
└────────┬────────┘
         │ Task: Request → In Transit
         │ ✓ Complete: Transport departs
         │
         v
┌─────────────────┐
│  TRANSPORTER    │
│ Delivers Order  │
└────────┬────────┘
         │ Task: Assignment → Site Receipt
         │ ✓ Complete: Delivered + Receipt logged
         │
         v
┌─────────────────┐
│   CONSULTANT    │
│  Logs Receipt   │
└─────────────────┘
```

---

## 📊 Grading Impact

### Performance Score Components (Total: 100 points)

**1. Completion Rate (40 points)**
- % of tasks completed vs total tasks
- Example: 18 completed / 20 total = 90% = 36 points

**2. Efficiency/Timeliness (30 points)**
- Average days to complete tasks
  - < 2 days: 30 points ⚡
  - 2-5 days: 20 points ✅
  - 5-10 days: 10 points ⏰
  - > 10 days: 0 points ⚠️

**3. Volume/Productivity (30 points)**
- Total number of completed tasks
  - ≥ 50 tasks: 30 points 🚀
  - 30-49 tasks: 25 points 📈
  - 10-29 tasks: 15 points 📊
  - 1-9 tasks: 5 points 📉

---

## 🎓 Example Scenarios

### Scenario 1: Schedule Officer Performance
```
Tasks Created: 25 material requests
Completed: 22 have site receipts
Avg Days: 8 days (request to receipt)

Grade Calculation:
- Completion: 22/25 = 88% → 35.2 points
- Efficiency: 8 days → 10 points
- Volume: 22 tasks → 15 points
- TOTAL: 60.2 points → Grade D
```

### Scenario 2: Storekeeper Performance
```
Tasks Assigned: 30 orders
Completed: 28 are in transit
Avg Days: 3 days (receipt to departure)

Grade Calculation:
- Completion: 28/30 = 93% → 37.2 points
- Efficiency: 3 days → 20 points
- Volume: 28 tasks → 15 points
- TOTAL: 72.2 points → Grade C+
```

### Scenario 3: Transporter Performance
```
Transports Assigned: 45
Completed: 42 delivered with receipts
Avg Days: 1.5 days (assignment to receipt)

Grade Calculation:
- Completion: 42/45 = 93% → 37.2 points
- Efficiency: 1.5 days → 30 points
- Volume: 42 tasks → 25 points
- TOTAL: 92.2 points → Grade A+
```

---

## 💡 Key Insights

### For Schedule Officers:
- You're evaluated on the entire supply chain
- Faster processing downstream improves your grade
- Follow up with storekeepers and transporters for better scores

### For Storekeepers:
- Quick processing and timely transport release is key
- Your grade improves when transports depart quickly
- Coordinate with transporters for smooth handoffs

### For Transporters:
- Delivery speed AND site receipt logging both matter
- Work with consultants to ensure timely receipt logging
- Multiple quick deliveries boost your volume score

---

## 🔧 Technical Implementation

### Files Modified:
- `/Inventory/views.py` - Updated `management_dashboard` view
- `USER_PERFORMANCE_GRADING_SYSTEM.md` - Updated documentation

### Key Changes:
1. **Schedule Officers**: Changed completion from status-based to site receipt-based
2. **Storekeepers**: Changed completion from processed quantity to "In Transit" status
3. **Transporters**: Changed completion from "Delivered" to "Delivered + Site Receipt"

### Database Queries:
- All queries use proper field relationships (ForeignKey, reverse relations)
- Efficient queries with `.distinct()` to avoid duplicates
- Proper date calculations using model datetime fields

---

## ✅ Validation

The system ensures:
- ✅ No double-counting of tasks
- ✅ Accurate completion status based on workflow stages
- ✅ Fair comparison across roles (different tasks, same scoring)
- ✅ Real-time calculation on each dashboard load
- ✅ Fallback to default values if calculation fails

---

## 📈 Expected Improvements

With this update:
- **More Accurate**: Grades reflect actual workflow completion
- **Fair Assessment**: Each role evaluated at their handoff point
- **Actionable**: Clear what needs to improve for better grades
- **Motivating**: Recognizes role-specific contributions
- **Collaborative**: Encourages smooth handoffs between teams

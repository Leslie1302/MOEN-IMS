# User Performance Grading System

## Overview
The comprehensive user performance grading system evaluates all staff members based on their role-specific tasks, measuring three key dimensions: **Completion Rate**, **Efficiency/Timeliness**, and **Volume/Productivity**.

## Grading Formula

### Performance Score (Out of 100)
The total performance score is calculated from three weighted components:

1. **Completion Rate (40 points)**
   - Percentage of tasks completed vs total tasks assigned
   - Formula: `(completed_tasks / total_tasks) × 40`

2. **Efficiency/Timeliness (30 points)**
   - Average days to complete tasks (lower is better)
   - Scoring tiers:
     - **30 points**: < 2 days (Excellent)
     - **20 points**: 2-5 days (Good)
     - **10 points**: 5-10 days (Average)
     - **0 points**: > 10 days (Needs Improvement)

3. **Volume/Productivity (30 points)**
   - Total number of completed tasks
   - Scoring tiers:
     - **30 points**: ≥ 50 tasks (High productivity)
     - **25 points**: 30-49 tasks (Good productivity)
     - **15 points**: 10-29 tasks (Moderate productivity)
     - **5 points**: 1-9 tasks (Low productivity)
     - **0 points**: 0 tasks (No activity)

### Grade Letters
Based on the total performance score:

| Score Range | Grade | Color | Meaning |
|------------|-------|-------|---------|
| 90-100 | A+ | Success (Green) | Outstanding |
| 85-89 | A | Success (Green) | Excellent |
| 80-84 | B+ | Info (Blue) | Very Good |
| 75-79 | B | Info (Blue) | Good |
| 70-74 | C+ | Warning (Yellow) | Satisfactory |
| 65-69 | C | Warning (Yellow) | Acceptable |
| 60-64 | D | Danger (Red) | Needs Improvement |
| < 60 | F | Danger (Red) | Unsatisfactory |
| No tasks | N/A | Secondary (Gray) | No activity |

## Workflow Overview

```
SCHEDULE OFFICER          STOREKEEPER              TRANSPORTER            CONSULTANT
     |                         |                         |                      |
     | Creates Request         |                         |                      |
     |------------------------>|                         |                      |
     | (Task Starts)           |                         |                      |
     |                         | Processes Materials     |                      |
     |                         | (Task Starts)           |                      |
     |                         |------------------------>|                      |
     |                         | Assigns Transport       |                      |
     |                         | (Task Completes ✓)     |                      |
     |                         |                         | Receives Assignment  |
     |                         |                         | (Task Starts)        |
     |                         |                         |                      |
     |                         |                         | Delivers Materials   |
     |                         |                         |--------------------->|
     |                         |                         |                      | Logs Receipt
     |                         |                         | (Task Completes ✓)  |
     | (Task Completes ✓)     |                         |                      |
     |<--------------------------------------------------------------------|
```

**Key Points:**
- Schedule Officers: Start-to-finish responsibility (Request → Site Receipt)
- Storekeepers: Process and handoff (Request → In Transit)
- Transporters: Delivery and confirmation (Assignment → Site Receipt)
- All roles measured on completion rate, speed, and volume

---

## Role-Specific Task Tracking

### 1. Schedule Officers
**Tracked Tasks:**
- Material requests they create (20 requests = 20 tasks)

**Completion Criteria:**
- ✅ Task Complete: When site receipt is logged for the order
- Entire workflow: Request → Processing → Transport → Delivery → **Site Receipt**

**Efficiency Measurement:**
- Days from request creation to site receipt logging
- Measures end-to-end process efficiency

**Why This Matters:**
- Schedule Officers own the complete lifecycle
- Their success depends on the entire supply chain
- Site receipt confirms materials reached the intended site

---

### 2. Storekeepers
**Tracked Tasks:**
- Material orders they process (same orders as Schedule Officers)
- Tasks = Number of orders assigned to them

**Completion Criteria:**
- ✅ Task Complete: When transport status becomes "In Transit"
- Their workflow: Receive Request → Process Materials → Release to Transport → **In Transit**

**Efficiency Measurement:**
- Days from request receipt to transport departure (In Transit status)
- Measures processing and loading efficiency

**Why This Matters:**
- Storekeepers hand off to Transporters
- "In Transit" confirms materials successfully processed and loaded
- Their responsibility ends when transport departs

---

### 3. Transporters
**Tracked Tasks:**
- Transport assignments they receive
- Tasks = Number of transport assignments

**Completion Criteria:**
- ✅ Task Complete: When status is "Delivered" **AND** site receipt is logged
- Their workflow: Receive Assignment → Load → Depart → Deliver → **Wait for Site Receipt**

**Efficiency Measurement:**
- Days from transport assignment to site receipt logging
- Measures delivery and handover efficiency

**Why This Matters:**
- Transporters must ensure proper delivery AND confirmation
- Site receipt validates successful handover to site
- Their responsibility includes getting receipt logged

### 4. Consultants
**Tracked Tasks:**
- Site receipts logged
- Material confirmations recorded

**Completion Criteria:**
- Site receipts with status `Received`

**Efficiency Measurement:**
- Same-day logging is considered optimal (1 day)

### 5. Management
**Tracked Tasks:**
- Orders reviewed and approved
- Oversight actions taken

**Completion Criteria:**
- Orders updated with status `Approved` or `Completed`

**Efficiency Measurement:**
- Days from submission to approval/completion

## Worker of the Month

### Selection Criteria
- **Automatic Selection**: The user with the highest performance score
- **Minimum Requirement**: Must have a score > 0 (some activity)
- **Display**: Highlighted row with 🏆 trophy badge
- **Recognition**: Badge reads "Worker of the Month"

### Tie-Breaking
If multiple users have the same top score:
- First user in the sorted list is selected
- Consider manual review for multiple top performers

## Dashboard Display

### Performance Metrics Shown
1. **Performance Score**: Visual progress bar (0-100%)
2. **Grade Letter**: Color-coded badge (A+ through F)
3. **Tasks**: Completed / Total with badge
4. **Efficiency**: Average days with color coding
5. **Sub-metrics**: Completion rate and volume in tooltip

### Color Coding
- **Green**: Top performers (A grades)
- **Blue**: Strong performers (B grades)
- **Yellow**: Average performers (C grades)
- **Red**: Underperformers (D-F grades)
- **Gray**: No activity (N/A)

## Usage Guidelines

### For Management
- Review performance dashboard regularly
- Identify top performers for recognition
- Spot users needing additional support
- Use metrics for performance reviews

### For Staff
- Track your own performance via staff profile
- Understand what contributes to your grade
- Focus on all three dimensions (completion, speed, volume)
- Strive for balanced performance across metrics

## Technical Implementation

### Data Sources
- `MaterialOrder` model (requests and completions)
- `MaterialTransport` model (deliveries)
- `SiteReceipt` model (site confirmations)
- User `last_updated_by` field (processing actions)

### Update Frequency
- Calculated on each dashboard page load
- Real-time reflection of current performance
- No caching to ensure accuracy

### Error Handling
- Individual user calculation errors logged
- Failed calculations default to N/A grade
- System continues even if some users fail

## Future Enhancements

### Potential Additions
1. **Time-based filtering**: Monthly, quarterly, yearly performance
2. **Historical tracking**: Performance trends over time
3. **Team comparisons**: Department or role-based rankings
4. **Performance alerts**: Notifications for significant changes
5. **Custom weights**: Adjustable scoring formula per organization needs
6. **Multi-factor rewards**: Additional recognition criteria

### Recommendations
- Regular review and calibration of scoring thresholds
- Gather staff feedback on fairness and motivation
- Consider seasonal workload variations
- Document organizational performance standards

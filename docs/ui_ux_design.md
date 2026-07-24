# UI/UX Design Specification: AI-Powered TPM

This document provides the complete user interface and user experience design specifications for the AI-Powered Technical Project Manager (AI-TPM). 

To comply with project specifications, **no application code is generated**. Instead, this document details screen layouts, widget positions, typography, user flows, accessibility criteria, loading/empty states, and dark mode rules.

---

## 1. Design System & Global Styles

### Color Palette (Tailored HSL Design)

| Token | Light Mode Value | Dark Mode Value | Usage |
| :--- | :--- | :--- | :--- |
| **Primary (Brand)** | `hsl(220, 90%, 56%)` (Blue) | `hsl(217, 91%, 60%)` (Bright Blue) | Core actions, primary buttons, active states. |
| **Secondary (Muted)**| `hsl(215, 16%, 47%)` (Slate) | `hsl(215, 20%, 65%)` (Muted Slate) | Subtitles, helper texts, secondary borders. |
| **Background (Base)** | `hsl(0, 0%, 100%)` (White) | `hsl(222, 47%, 11%)` (Deep Obsidian) | Main app canvas background. |
| **Background (Card)** | `hsl(210, 40%, 98%)` (Soft Grey) | `hsl(223, 47%, 16%)` (Obsidian Card) | Component backplanes, widgets, dashboards. |
| **Border (Default)** | `hsl(214, 32%, 91%)` (Soft Border) | `hsl(223, 47%, 22%)` (Dark Border) | Table dividers, inputs, container borders. |
| **Warning/Danger** | `hsl(0, 84%, 60%)` (Soft Red) | `hsl(0, 84%, 60%)` (Crimson Alert) | Red alert indicators, blockers, critical errors. |

### Typography
* **Primary Font**: Inter (Variable) for main UI elements, charts, and tables.
* **Secondary Font**: Outfit (Variable) for hero headers, titles, and KPI values.
* **Monospace Font**: Fira Code for code blocks, terminal traces, and prompt managers.

---

## 2. Global Layout Structure

The app uses a **Collapsible Sidebar Layout** (Desktop) and a **Bottom Nav / Hamburger Drawer** (Mobile).

```
 ┌────────────────────────────────────────────────────────┐
 │ Sidebar (Navigation)  │ Header (Global Search, Alert)  │
 │                       ├────────────────────────────────┤
 │ Workspace List        │                                │
 │ Core Pages Links      │           Dashboard            │
 │ Settings Link         │            Viewport            │
 │                       │                                │
 └───────────────────────┴────────────────────────────────┘
```

---

## 3. Screen Designs & Specifications

### 1. Login Page
* **Purpose**: Tenant credentials validation and OAuth provider connections.
* **Widgets**: Center card with input text fields (Email, Password), Login Button, GitHub Sign-In Button, Workspace selector.
* **User Flow**: User enters credentials -> Click Log In -> App verifies JWT -> User is redirected to Dashboard.
* **Empty/Loading/Error States**: Loading: Login button changes to spinner. Error: Field inputs highlight red; RFC 7807 problem message appears as an alert banner.
* **Accessibility**: `aria-required="true"` on inputs. Form responds to `Enter` key.
* **Responsive / Dark Mode**: Stacked card layout on mobile. High contrast input fields.

### 2. Main Dashboard
* **Purpose**: Overview of workspace KPI metrics, blocker notifications, and active agent execution status.
* **Widgets**: KPI Grid (Sprint Velocity, PR Cycle Time, Active Blockers), Blocker Feed list, Active Agents grid.
* **Charts**: Recharts Line Chart showing Sprint Velocity trend.
* **Filters**: Project Selector (`All Projects` vs `Selected Project`).
* **Actions**: Click blocker to view task, Click agent to open execution console.
* **Empty State**: Displays *"No active projects in workspace. Connect your first integration to get started."* with a button pointing to Integrations.

### 3. Workspace Explorer
* **Purpose**: Manage workspaces and logical grouping of team projects.
* **Widgets**: Grid of Workspace cards (Name, number of projects, team size, connection status indicators).
* **Filters**: Sort by Name, Created Date, Team Size.
* **Actions**: `Create New Workspace` button (triggers modal dialog), Delete Workspace (requires confirmation).
* **Loading State**: Skeleton card layouts with animated background gradients.

### 4. Project Overview
* **Purpose**: Central hub for a single project, displaying repository activities and linked epics.
* **Widgets**: Connected repositories grid, Active Epic Gantt Chart, Project Team members list.
* **Actions**: Add Repository (modal popup), Sync Project Context (triggers manual poll).
* **Accessibility**: Keyboard navigation enabled for gantt chart elements.

### 5. Sprint Overview
* **Purpose**: Real-time sprint progress monitoring and backlog health checks.
* **Widgets**: Kanban Board (To Do, In Progress, Review, Done columns), Sprint Burn-Down chart, Scope Change logs.
* **Charts**: Burn-Down Chart (Ideal path vs Actual completed points).
* **Actions**: Drag-and-drop task transition, Create task ticket (triggers modal).

### 6. Developer Workload Panel
* **Purpose**: High-level workload visualizer showing active task allocation per developer.
* **Widgets**: Developer Load list showing assigned points, average velocity, and overload warnings.
* **Charts**: Stacked horizontal bar chart (Task priority distribution per user).
* **Filters**: Role filtering (`Developer`, `Designer`, `QA`).

### 7. GitHub Dashboard
* **Purpose**: Detailed repository analysis and code review telemetry.
* **Widgets**: Repo health card, commit activity streams, test pipeline runs status list.
* **Charts**: Commit frequency bar chart.
* **Actions**: Link new repository, trigger manual code analysis scan.

### 8. PR Monitor
* **Purpose**: Track open pull requests, review statuses, and pipeline blockers.
* **Widgets**: PR status list, review turnaround timer card, review coverage gauge.
* **Filters**: Sort by Open Date, Size, Unresolved Comments count.
* **Actions**: Request review reassignment, trigger tests re-run.

### 9. Jira Dashboard
* **Purpose**: Manage Jira boards, sprint scopes, and epic dependencies.
* **Widgets**: Sprint performance card, ticket priority distribution, blockages list.
* **Charts**: Ticket Priority pie chart.
* **Actions**: Link new Jira board, trigger ticket sync task.

### 10. Calendar
* **Purpose**: Schedule synchronization, team meetings, and availability tracking.
* **Widgets**: Interactive weekly/monthly calendar grid, active meeting agendas list.
* **Actions**: Auto-schedule standup (triggers Calendar Agent), add calendar override.
* **Responsive**: Monthly grid collapses to daily list view on mobile.

### 11. Slack Activity
* **Purpose**: Monitor project communication history, activity feeds, and discussion summaries.
* **Widgets**: Active threads grid, context-engine summarized topic lists, sentiment trends.
* **Filters**: Filter by channel name, filter by user mentions.

### 12. Knowledge Graph
* **Purpose**: Interactive network visualization showing relationships between commits, tickets, users, and tasks.
* **Widgets**: Vis.js/D3 canvas window showing nodes and relationship lines, detail sidebar.
* **Filters**: Node type filters (Toggle `PRs`, `Issues`, `Developers`).
* **Actions**: Search node (highlights selected node on canvas), export graph state.
* **Accessibility**: Alternative list view displaying all node properties for screen readers.

### 13. Recommendations Console
* **Purpose**: List actionable, AI-generated optimizations and risk warnings.
* **Widgets**: Stack of recommendation cards ordered by score, detail view pane.
* **Actions**: Dismiss recommendation (logs feedback), Accept recommendation (triggers workflow).
* **Empty State**: Displays *"All clear! No project risks detected."* with a green shield icon.

### 14. Analytics Panel
* **Purpose**: Detailed time-series reports for sprint velocity and lead/cycle times.
* **Widgets**: KPI cards, historical trends viewer.
* **Charts**: Line charts for cycle times and lead times, bar charts for deployment frequencies.
* **Actions**: Export report data (CSV/PDF).

### 15. Workflow Builder
* **Purpose**: Visual drag-and-drop editor for workflow DAGs.
* **Widgets**: Node sidebar (Triggers, Agents, Actions, Approvals), canvas viewport, parameter editing panel.
* **Actions**: Add step node, connect nodes (create transition edge), save workflow, validate DAG logic.
* **Loading State**: Displays skeleton flow nodes with animated loading boundaries.

### 16. Agent Console
* **Purpose**: Monitor agent activity, prompt versions, and thought logs.
* **Widgets**: Agent statuses table, real-time thought log console, prompt version history list.
* **Actions**: Force-terminate agent run, edit active prompt template.

### 17. Approval Center
* **Purpose**: Review pending, automated, or manual task executions.
* **Widgets**: Queue of pending approval request cards (Tool parameters, reasoning details, risk score), past history table.
* **Actions**: Approve action (executes tool call), Deny action (cancels workflow step).
* **Empty State**: Displays *"No pending approvals. Enjoy the flow!"* with a green checkmark.

### 18. Notification Center
* **Purpose**: Central log of personal updates, mentions, and approval requests.
* **Widgets**: Notification list grouped by priority (High, Medium, Low), notification categories filter.
* **Actions**: Mark all as read, configure notification delivery preferences.

### 19. Audit Logs Viewer
* **Purpose**: Read-only viewer for security logs.
* **Widgets**: Audit event log data table (Timestamp, User URN, Action Category, details JSON).
* **Filters**: Date range picker, User email filter, Action category filter.
* **Actions**: Export audit history.

### 20. Settings Console
* **Purpose**: Manage organization, tenant details, domains, and global configurations.
* **Widgets**: Org info editor form, connected workspaces settings, team member roles table.
* **Actions**: Save settings, add team member, remove team member.

### 21. Prompt Manager
* **Purpose**: Edit and test agent prompt templates.
* **Widgets**: Prompt versions list, markdown editor workspace, agent test runner window.
* **Actions**: Create new draft, push prompt version to production, test prompt execution.

### 22. Model Configuration
* **Purpose**: Configure LLM endpoints, temperature parameters, and token limit guidelines.
* **Widgets**: Model providers table, dynamic parameter sliders (Temperature, top_p, Max Tokens), pricing estimators.
* **Actions**: Save configurations, run model connectivity test.

### 23. Memory Explorer
* **Purpose**: Inspect pgvector semantic memories and database context snapshots.
* **Widgets**: Memory vectors database table, semantic search interface, vector details pane.
* **Actions**: Delete vector item, rebuild vector database index (triggers HNSW rebuild).

---

## 4. Universal Page States

### Loading States
* **Skeleton Screen Pattern**: Text sections are represented by grey blocks with a shimmer animation (`background-position` shift). Cards and tables are represented by empty containers with borders.

### Empty States
* Empty states are displayed using custom illustrations (e.g., clear skies for "No risks", checkboxes for "No approvals"), a descriptive subtitle, and a single, clear primary call to action (CTA).

### Error States
* **Problem Banners**: Global API errors display an orange or red banner detailing the issue.
* **Interactive Toasts**: Network timeout errors display a floating toast notification in the bottom right corner with a "Retry" button.
* **Field Highlights**: Form validation errors display inline helper text in red under the input field.

---

## 5. Accessibility (a11y) & Responsive Specs

### a11y Standards
* **Contrast Compliance**: Contrast ratio is kept above `4.5:1` for regular text and `3:1` for large text, adhering to WCAG 2.1 AA standards.
* **ARIA Roles**: Interactive elements utilize semantic HTML and ARIA roles (e.g., `role="dialog"`, `role="tablist"`).
* **Keyboard Shortcuts**:
  * `/`: Focus Global Search input.
  * `Esc`: Close open modal panels.
  * `g` + `d`: Navigate to Dashboard.
  * `g` + `a`: Navigate to Agent Console.

### Responsive Breakpoints
* **Mobile (up to 767px)**: Sidebar navigation collapses into a bottom navigation bar. Metric cards stack vertically.
* **Tablet (768px - 1023px)**: Sidebar collapses into an icon-only menu. Dashboards display in a 2-column layout.
* **Desktop (1024px and above)**: Full sidebar displays. Dashboards display in a 3-column layout.
* **Wide Monitor (1440px and above)**: Dashboard layout width is capped at `1440px` with central alignment to prevent visual stretching.

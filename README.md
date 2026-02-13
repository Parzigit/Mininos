# DLBMT: Distributed Load Balancing with Multi-level Thresholds

This project implements the **Distributed Load Balancing Mechanism with Multi-level Threshold (DLBMT)** for Software-Defined Networks (SDN). It provides a real-time simulation environment to demonstrate efficient switch migration strategies under varying traffic loads, using a sophisticated multi-controller architecture.

## Features

-   **Real-time SDN Simulation**: Simulates multiple controllers and switches with dynamic traffic generation and resource usage (CPU, Memory, Bandwidth).
-   **Multi-level Thresholding**: Implements the 4-level load classification system (Idle, Normal, High, Overload) from the research paper.
-   **Intelligent Migration**: Automatically selects the best switch to migrate based on:
    -   **Load Imbalance Degree**: Minimizing variance between controller loads.
    -   **Migration Cost**: Accounting for distance and resource usage.
    -   **Migration Efficiency**: Maximizing impact while minimizing cost.
-   **Interactive Dashboard**:
    -   Visualizes network topology with drag-and-drop support.
    -   Real-time charts for global load and imbalance.
    -   Detailed metrics for every controller and switch.
    -   Controls for traffic patterns (Wave, Uniform, Burst) and simulation speed.

##  Project Structure

The project is organized as follows:

```
btp-new/
├── dlbmt/
│   ├── app.py                 # Main Flask application (Backend API + WebSocket)
│   ├── dlbmt_engine.py        # Core algorithm implementation (Eq 1-10)
│   ├── sdn_simulator.py       # Simulation logic (Topology, State management)
│   ├── traffic_generator.py   # Traffic pattern generation
│   ├── requirements.txt       # Python dependencies
│   └── frontend/              # React + Vite Frontend
│       ├── src/               # React source code
│       ├── dist/              # Compiled static assets (served by Flask)
│       └── package.json       # Frontend dependencies
├── paper.txt                  # Research paper text (reference)
└── README.md                  # This file
```

##  Prerequisites

-   **Python 3.8+**
-   **Node.js 16+** (Only if you plan to modify and rebuild the frontend)

##  Installation & Setup

### 1. Backend Setup

The backend is built with Python and Flask.

1.  Navigate to the project directory:
    ```bash
    cd btp-new/dlbmt
    ```

2.  (Optional) Create a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### 2. Running the Application

This project is designed to run as a single integrated application where Flask serves the frontend.

1.  Start the server:
    ```bash
    python app.py
    ```

2.  Open your browser and visit:
    ```
    http://localhost:5000
    ```

### 3. Frontend Development (Optional)

If you want to modify the React frontend:

1.  Navigate to the frontend directory:
    ```bash
    cd btp-new/dlbmt/frontend
    ```

2.  Install Node.js dependencies:
    ```bash
    npm install
    ```

3.  Run the development server (with hot reload):
    ```bash
    npm run dev
    ```
    *Note: The dev server runs on port 5173, but it expects the backend to be running on 5000.*

4.  To build for production (updates `dist/` folder):
    ```bash
    npm run build
    ```

##  Algorithm Explanation

The core logic resides in `dlbmt_engine.py` and strictly follows the mathematical model of the DLBMT paper.

### 1. Load Calculation
The load of a switch (\$L_{sji}$) on a controller is calculated as a weighted sum of CPU, Memory, and Bandwidth usage:
$$ £_{ji} = \alpha \cdot \frac{L_{CPU}}{C_{CPU}} + \beta \cdot \frac{L_{MEM}}{C_{MEM}} + \gamma \cdot \frac{L_{BW}}{C_{BW}} $$
*(Where $\alpha + \beta + \gamma = 1$)*

The total load on a controller ($LR_{cj}$) is the sum of loads of all managed switches.

### 2. Multi-level Thresholds
Controllers are classified into 4 levels based on their load percentage:
-   **Idle**: Load < 25%
-   **Normal**: 25% ≤ Load < 50%
-   **High**: 50% ≤ Load < 75%
-   **Overload**: Load ≥ 75%

### 3. Switch Migration Decision
When a controller enters the **High** or **Overload** state, the system searches for a migration partner:
1.  **Candidate Selection**: Switches with a high resource-to-distance ratio are candidates.
2.  **Target Selection**: Idle or Normal controllers are evaluated as targets.
3.  **Efficiency Calculation**: The system calculates "Migration Efficiency" ($\vartheta_{jk}$) which balances the improvement in load balance against the cost of migration (distance * load).
4.  **Execution**: The switch-target pair with the best efficiency is selected, and the switch is migrated.

## API Endpoints

-   `GET /api/topology`: Returns current nodes and links.
-   `GET /api/stats/summary`: Returns global load, imbalance, and migration stats.
-   `GET /api/migration/history`: Returns log of all past migrations.
-   `POST /api/config/traffic`: Update traffic pattern (e.g., `{"pattern": "wave", "intensity": 2.0}`).
-   `POST /api/migration/trigger`: Manually force a load balancing selection cycle.

## Contributing

1.  Fork the repository.
    2. Create a feature branch.
    3. Commit changes.
    4. Push to the branch.
    5. Open a Pull Request.

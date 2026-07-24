from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any

class PredictiveAnalyticsEngine:
    """Statistical and heuristic prediction engine for sprint velocity, burndown trajectories, and delivery risk."""

    @staticmethod
    def calculate_burndown(
        total_points: float,
        completed_points: float,
        total_days: int = 14,
        elapsed_days: int = 7
    ) -> List[Dict[str, Any]]:
        """Calculate daily ideal vs actual remaining story points trajectory."""
        burndown_data = []
        ideal_decrement_per_day = total_points / max(1, total_days)
        actual_velocity_per_day = completed_points / max(1, elapsed_days)

        current_actual = total_points

        for day in range(total_days + 1):
            ideal_remaining = max(0.0, round(total_points - (day * ideal_decrement_per_day), 2))
            
            if day <= elapsed_days:
                actual_remaining = max(0.0, round(total_points - (day * actual_velocity_per_day), 2))
            else:
                actual_remaining = None

            burndown_data.append({
                "day": day,
                "ideal_remaining": ideal_remaining,
                "actual_remaining": actual_remaining
            })

        return burndown_data

    @staticmethod
    def predict_completion_date(
        total_points: float,
        completed_points: float,
        elapsed_days: int = 7,
        total_sprint_days: int = 14
    ) -> Dict[str, Any]:
        """Predict sprint completion date and delay probability based on current velocity."""
        remaining_points = max(0.0, total_points - completed_points)
        daily_velocity = completed_points / max(1, elapsed_days)

        if daily_velocity > 0:
            estimated_days_needed = remaining_points / daily_velocity
        else:
            estimated_days_needed = remaining_points * 2.0 # Penalty for 0 velocity

        total_estimated_days = elapsed_days + estimated_days_needed
        delay_days = max(0.0, total_estimated_days - total_sprint_days)

        if delay_days == 0:
            delay_probability = 0.05
        elif delay_days <= 2:
            delay_probability = 0.35
        elif delay_days <= 5:
            delay_probability = 0.70
        else:
            delay_probability = 0.95

        predicted_date = datetime.now(timezone.utc) + timedelta(days=estimated_days_needed)

        return {
            "daily_velocity": round(daily_velocity, 2),
            "estimated_days_remaining": round(estimated_days_needed, 1),
            "total_estimated_sprint_days": round(total_estimated_days, 1),
            "delay_days": round(delay_days, 1),
            "delay_probability": round(delay_probability, 2),
            "predicted_completion_date": predicted_date.strftime("%Y-%m-%d")
        }

    @staticmethod
    def predict_risk_score(
        total_tasks: int,
        completed_tasks: int,
        critical_open_tasks: int,
        unassigned_tasks: int
    ) -> Dict[str, Any]:
        """Predict overall delivery risk score and primary risk factors."""
        if total_tasks == 0:
            return {"risk_score": 0.0, "risk_level": "low", "risk_factors": []}

        incomplete_tasks = total_tasks - completed_tasks
        incomplete_ratio = incomplete_tasks / total_tasks
        critical_ratio = critical_open_tasks / max(1, total_tasks)
        unassigned_ratio = unassigned_tasks / max(1, total_tasks)

        # Weighted multi-factor risk score
        raw_score = (incomplete_ratio * 0.4) + (critical_ratio * 0.4) + (unassigned_ratio * 0.2)
        risk_score = round(min(1.0, max(0.0, raw_score)), 2)

        if risk_score >= 0.7:
            risk_level = "critical"
        elif risk_score >= 0.4:
            risk_level = "high"
        elif risk_score >= 0.2:
            risk_level = "medium"
        else:
            risk_level = "low"

        risk_factors = []
        if critical_open_tasks > 0:
            risk_factors.append(f"{critical_open_tasks} critical/high priority tasks remaining uncompleted.")
        if unassigned_tasks > 0:
            risk_factors.append(f"{unassigned_tasks} tasks lack assigned owner.")
        if incomplete_ratio > 0.6:
            risk_factors.append(f"High ratio of incomplete tasks ({incomplete_tasks}/{total_tasks}).")

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors
        }


import random

class MonteCarloPredictor:
    """Monte Carlo Probabilistic Simulation Engine sampling 1,000 sprint velocity trajectories."""

    @staticmethod
    def run_simulation(
        historical_velocities: List[float],
        remaining_points: float,
        num_simulations: int = 1000,
        sprint_days_left: int = 7
    ) -> Dict[str, Any]:
        """Run 1,000-run Monte Carlo simulation to compute P50, P80, P95 completion forecasts."""
        if not historical_velocities:
            historical_velocities = [5.0, 8.0, 6.0, 7.0, 4.0]

        if remaining_points <= 0:
            return {
                "num_simulations": num_simulations,
                "p50_days": 0.0,
                "p80_days": 0.0,
                "p95_days": 0.0,
                "completion_prob_on_time": 1.0,
                "predicted_p50_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
            }

        simulated_days_needed: List[float] = []

        for _ in range(num_simulations):
            pts = remaining_points
            days = 0
            while pts > 0 and days < 100:
                daily_vel = random.choice(historical_velocities) / 14.0 # Daily velocity
                daily_vel = max(0.1, daily_vel + random.gauss(0, 0.2))
                pts -= daily_vel
                days += 1
            simulated_days_needed.append(days)

        simulated_days_needed.sort()
        p50_idx = int(num_simulations * 0.50)
        p80_idx = int(num_simulations * 0.80)
        p95_idx = int(num_simulations * 0.95)

        p50_days = simulated_days_needed[p50_idx]
        p80_days = simulated_days_needed[p80_idx]
        p95_days = simulated_days_needed[p95_idx]

        on_time_count = sum(1 for d in simulated_days_needed if d <= sprint_days_left)
        prob_on_time = round(on_time_count / num_simulations, 2)

        p50_date = datetime.now(timezone.utc) + timedelta(days=p50_days)

        return {
            "num_simulations": num_simulations,
            "p50_days": p50_days,
            "p80_days": p80_days,
            "p95_days": p95_days,
            "completion_prob_on_time": prob_on_time,
            "predicted_p50_date": p50_date.strftime("%Y-%m-%d")
        }


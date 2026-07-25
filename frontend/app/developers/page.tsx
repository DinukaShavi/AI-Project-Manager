"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { jiraApi } from "../../api";
import { Users, Award, ShieldAlert, CheckCircle2, TrendingUp } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function DevelopersPage() {
  const [team, setTeam] = useState<any[]>([
    { assignee: "Dinuka Shavi", assigned_issues: 5, total_story_points: 18, capacity_percentage: 90.0, tsr: "95%" },
    { assignee: "Dev Lead", assigned_issues: 3, total_story_points: 12, capacity_percentage: 60.0, tsr: "98%" },
    { assignee: "Frontend Lead", assigned_issues: 2, total_story_points: 8, capacity_percentage: 40.0, tsr: "92%" },
  ]);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await jiraApi.getWorkload(DUMMY_ORG_ID);
        if (res && res.team_workload) setTeam(res.team_workload);
      } catch (e) {
        // Fallback
      }
    }
    loadData();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="developers" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Users className="w-8 h-8 text-blue-400" /> Developer Workload & Performance Metrics
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Engineering capacity distribution, story point allocation, and velocity efficiency.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {team.map((member) => (
              <div key={member.assignee} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center font-bold text-lg text-white">
                    {member.assignee.charAt(0)}
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">{member.assignee}</h3>
                    <p className="text-xs text-slate-400">{member.assigned_issues} Active Issues • {member.total_story_points} Points</p>
                  </div>
                </div>

                <div className="space-y-2 pt-2 border-t border-white/5">
                  <div className="flex justify-between text-xs text-slate-300">
                    <span>Capacity Utilization</span>
                    <span className="font-bold text-blue-400">{member.capacity_percentage}%</span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2">
                    <div className="bg-gradient-to-r from-blue-500 to-indigo-500 h-2 rounded-full" style={{ width: `${member.capacity_percentage}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

import React from "react";
import { Users, AlertTriangle, CheckCircle2, UserCheck, ShieldAlert } from "lucide-react";

interface Props {
  workload: any[];
}

export default function DeveloperWorkloadPanel({ workload }: Props) {
  const defaultWorkload = workload.length > 0 ? workload : [
    { assignee: "Dinuka Shavi", assigned_issues: 5, total_story_points: 18, capacity_percentage: 90.0 },
    { assignee: "Dev Lead", assigned_issues: 3, total_story_points: 12, capacity_percentage: 60.0 },
    { assignee: "Frontend Lead", assigned_issues: 2, total_story_points: 8, capacity_percentage: 40.0 },
  ];

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Developer Workload & Capacity</h3>
            <p className="text-xs text-slate-400">Task distribution and availability tracking</p>
          </div>
        </div>

        <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20 flex items-center gap-1">
          <ShieldAlert className="w-3.5 h-3.5" /> 1 Developer Near Capacity
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        {defaultWorkload.map((dev) => {
          const isOverloaded = dev.capacity_percentage >= 85;
          return (
            <div
              key={dev.assignee}
              className={`p-4 rounded-xl border backdrop-blur-xl transition-all ${
                isOverloaded
                  ? "bg-amber-500/5 border-amber-500/30"
                  : "bg-white/5 border-white/5"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center font-bold text-xs text-blue-300">
                    {dev.assignee.charAt(0)}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">{dev.assignee}</h4>
                    <p className="text-[11px] text-slate-400">{dev.assigned_issues} active tasks • {dev.total_story_points} pts</p>
                  </div>
                </div>
                {isOverloaded ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                ) : (
                  <UserCheck className="w-4 h-4 text-emerald-400" />
                )}
              </div>

              <div className="mt-3 space-y-1">
                <div className="flex justify-between text-[11px]">
                  <span className="text-slate-400">Capacity Load</span>
                  <span className={isOverloaded ? "text-amber-400 font-bold" : "text-emerald-400 font-bold"}>
                    {dev.capacity_percentage}%
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-2 rounded-full ${
                      isOverloaded
                        ? "bg-gradient-to-r from-amber-500 to-orange-500"
                        : "bg-gradient-to-r from-emerald-500 to-teal-500"
                    }`}
                    style={{ width: `${dev.capacity_percentage}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

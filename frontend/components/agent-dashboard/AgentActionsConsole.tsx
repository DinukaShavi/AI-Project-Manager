"use client";

import React, { useState } from "react";
import { executeAgentPersona, createProjectTask } from "../../lib/api";
import { Bot, Send, Calendar, Ticket, MessageSquare, CheckCircle2, RefreshCw } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";
const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function AgentActionsConsole() {
  const [selectedAction, setSelectedAction] = useState<"jira" | "pr_comment" | "calendar" | "slack">("jira");
  const [inputTitle, setInputTitle] = useState("Configure Slack & GitHub Webhook HMAC Verification");
  const [inputDetails, setInputDetails] = useState("High priority security enhancement for webhook ingestion pipeline.");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleExecuteAction = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      if (selectedAction === "jira") {
        const res = await createProjectTask({
          project_id: DUMMY_PROJECT_ID,
          title: inputTitle,
          description: inputDetails,
          status: "todo",
          priority: "high",
          story_points: 5,
        });
        setResult({ status: "success", action: "Jira Task Created", details: res });
      } else if (selectedAction === "pr_comment") {
        const res = await executeAgentPersona(
          "TechnicalPMAgent",
          `Post PR comment: "${inputTitle}" - ${inputDetails}`,
          DUMMY_ORG_ID,
          DUMMY_PROJECT_ID
        );
        setResult({ status: "success", action: "Commented on PR #42", details: res });
      } else if (selectedAction === "calendar") {
        const res = await executeAgentPersona(
          "SprintPlanningAgent",
          `Schedule Google Calendar meeting: "${inputTitle}"`,
          DUMMY_ORG_ID,
          DUMMY_PROJECT_ID
        );
        setResult({ status: "success", action: "Google Meet Scheduled", details: res });
      } else if (selectedAction === "slack") {
        const res = await executeAgentPersona(
          "TechnicalPMAgent",
          `Send Slack channel notification: "${inputTitle}"`,
          DUMMY_ORG_ID,
          DUMMY_PROJECT_ID
        );
        setResult({ status: "success", action: "Slack Message Sent", details: res });
      }
    } catch (err: any) {
      setResult({ status: "error", message: err.message || "Execution failed" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-2xl">
      <div className="flex items-center gap-3">
        <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <Bot className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-white">AI Agent Autonomous Execution Console</h3>
          <p className="text-xs text-slate-400">Trigger multi-platform actions directly through the PM Kernel</p>
        </div>
      </div>

      {/* Action Selector Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
        <button
          type="button"
          onClick={() => { setSelectedAction("jira"); setInputTitle("Create Jira Ticket: OpenTelemetry Support"); }}
          className={`p-3 rounded-xl text-xs font-semibold border transition-all flex items-center justify-center gap-2 ${
            selectedAction === "jira"
              ? "bg-blue-600/20 text-blue-300 border-blue-500/40 shadow-lg shadow-blue-500/10"
              : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
          }`}
        >
          <Ticket className="w-4 h-4" /> Create Jira Task
        </button>

        <button
          type="button"
          onClick={() => { setSelectedAction("pr_comment"); setInputTitle("AI PR Review: Code diff approved with zero vulnerabilities"); }}
          className={`p-3 rounded-xl text-xs font-semibold border transition-all flex items-center justify-center gap-2 ${
            selectedAction === "pr_comment"
              ? "bg-purple-600/20 text-purple-300 border-purple-500/40 shadow-lg shadow-purple-500/10"
              : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
          }`}
        >
          <Send className="w-4 h-4" /> Comment on PR
        </button>

        <button
          type="button"
          onClick={() => { setSelectedAction("calendar"); setInputTitle("Schedule Standup: PR #42 Review Sync"); }}
          className={`p-3 rounded-xl text-xs font-semibold border transition-all flex items-center justify-center gap-2 ${
            selectedAction === "calendar"
              ? "bg-amber-600/20 text-amber-300 border-amber-500/40 shadow-lg shadow-amber-500/10"
              : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
          }`}
        >
          <Calendar className="w-4 h-4" /> Schedule Meeting
        </button>

        <button
          type="button"
          onClick={() => { setSelectedAction("slack"); setInputTitle("Slack Alert: Sprint velocity on track (61.8%)"); }}
          className={`p-3 rounded-xl text-xs font-semibold border transition-all flex items-center justify-center gap-2 ${
            selectedAction === "slack"
              ? "bg-emerald-600/20 text-emerald-300 border-emerald-500/40 shadow-lg shadow-emerald-500/10"
              : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
          }`}
        >
          <MessageSquare className="w-4 h-4" /> Send Slack Alert
        </button>
      </div>

      {/* Input Form */}
      <form onSubmit={handleExecuteAction} className="space-y-3 pt-2">
        <div>
          <label className="text-xs font-medium text-slate-300 block mb-1">Action Title / Subject</label>
          <input
            type="text"
            value={inputTitle}
            onChange={(e) => setInputTitle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-sm text-white focus:outline-none focus:border-purple-500"
            required
          />
        </div>

        <div>
          <label className="text-xs font-medium text-slate-300 block mb-1">Action Context & Parameters</label>
          <textarea
            value={inputDetails}
            onChange={(e) => setInputDetails(e.target.value)}
            rows={2}
            className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-sm text-white focus:outline-none focus:border-purple-500"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 via-indigo-600 to-emerald-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-purple-500/20 transition-all flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" /> Executing Action via AI Pipeline...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" /> Trigger Autonomous Action
            </>
          )}
        </button>
      </form>

      {/* Result Display */}
      {result && (
        <div className={`p-4 rounded-xl text-xs space-y-1 ${result.status === "success" ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20" : "bg-rose-500/10 text-rose-300 border border-rose-500/20"}`}>
          <div className="flex items-center gap-2 font-bold text-sm">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Action Executed: {result.action || "Success"}
          </div>
          <pre className="text-[11px] font-mono opacity-80 mt-1 overflow-x-auto">{JSON.stringify(result.details || result.message, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

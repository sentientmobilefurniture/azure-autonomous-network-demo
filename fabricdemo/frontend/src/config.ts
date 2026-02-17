// Hardcoded scenario configuration — single-scenario showcase.
// Replaces the dynamic ScenarioContext with compile-time constants.

export const SCENARIO = {
  name: "telco-noc",
  displayName: "Australian Telco NOC — Fibre Cut Incident",
  graph: "telco-noc-topology",
  runbooksIndex: "telco-noc-runbooks-index",
  ticketsIndex: "telco-noc-tickets-index",
  description:
    "A fibre cut on the Sydney-Melbourne corridor triggers a cascading alert " +
    "storm affecting enterprise VPNs, broadband, and mobile services. The AI " +
    "investigates root cause, blast radius, and remediation.",
  graphStyles: {
    nodeColors: {
      CoreRouter: "#38BDF8",
      AggSwitch: "#FB923C",
      BaseStation: "#A78BFA",
      TransportLink: "#3B82F6",
      MPLSPath: "#C084FC",
      Service: "#CA8A04",
      SLAPolicy: "#FB7185",
      BGPSession: "#F472B6",
    } as Record<string, string>,
    nodeSizes: {
      CoreRouter: 28,
      AggSwitch: 22,
      BaseStation: 18,
      TransportLink: 16,
      MPLSPath: 14,
      Service: 20,
      SLAPolicy: 12,
      BGPSession: 14,
    } as Record<string, number>,
    nodeIcons: {
      CoreRouter: "router",
      AggSwitch: "switch",
      BaseStation: "antenna",
      TransportLink: "link",
      MPLSPath: "path",
      Service: "service",
      SLAPolicy: "policy",
      BGPSession: "session",
    } as Record<string, string>,
  },
  exampleQuestions: [
    "What caused the alert storm on the Sydney-Melbourne corridor?",
    "Which enterprise services are affected by the fibre cut?",
    "How are MPLS paths rerouting around the failed transport link?",
    "What BGP sessions are down and what's their blast radius?",
    "Which SLA policies are at risk of being breached?",
    "Show me the correlation between optical power drops and service degradation",
  ],
};

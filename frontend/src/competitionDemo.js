export const DEFAULT_COMPETITION_DEMO_MESSAGE =
  "当前处于 Competition Demo Mode。已加载预置演示结果。如需处理新视频或重新生成 AI 内容，请配置 DEEPSEEK_API_KEY。";

export function normalizeCompetitionDemo(payload) {
  if (!payload?.enabled || !payload.workspace?.video_id) {
    return {
      enabled: false,
      apiKeyConfigured: false,
      message: "",
      label: "",
      workspace: null,
      summary: null,
      qaHistory: [],
    };
  }
  return {
    enabled: true,
    apiKeyConfigured: Boolean(payload.api_key_configured),
    message: payload.message || DEFAULT_COMPETITION_DEMO_MESSAGE,
    label: payload.label || "Preloaded Demo / Competition Demo",
    workspace: payload.workspace,
    summary: payload.summary || null,
    qaHistory: Array.isArray(payload.qa_history) ? payload.qa_history : [],
  };
}

export function competitionDemoCloudAiBlocked(demo) {
  return Boolean(demo?.enabled && !demo.apiKeyConfigured);
}

import { z } from 'zod';

export const AgentSchema = z.object({
  id: z.string(), name: z.string(), role: z.string(), description: z.string(),
  status: z.enum(['healthy', 'degraded', 'disabled','unknown']), version: z.string(),
  model: z.string(), prompt: z.string(), tools: z.array(z.string()),
  calls: z.number(), score: z.number().nullable(), latency: z.number(),
  maxTokens: z.number(), timeout: z.number(),
});
export const MailSchema = z.object({
  id: z.string(), sender: z.string(), address: z.string(), subject: z.string(),
  preview: z.string(), receivedAt: z.string(), category: z.enum(['REPLY_REQUIRED', 'REVIEW_REQUIRED', 'NO_REPLY']),
  confidence: z.number(), risk: z.enum(['low', 'medium', 'high']), priority: z.enum(['normal', 'high']),
  status: z.enum(['waiting', 'draft_saved', 'rejected','reviewed']), originalBody: z.string(), draftBody: z.string(),
  revision: z.number(), runId: z.string(), flags: z.array(z.string()), latestMessageId: z.string(), source:z.enum(['fixture','gmail']).optional(), draftId:z.string().nullable().optional(),
});
export const SpanSchema = z.object({
  id: z.string(), parentId: z.string().nullable(), name: z.string(), agentId: z.string(),
  type: z.enum(['chain', 'llm', 'tool', 'review']), status: z.enum(['success', 'waiting', 'error']),
  durationMs: z.number(), inputTokens: z.number().nullable(), outputTokens: z.number().nullable(),
  input: z.string(), output: z.string(), attempt: z.number(),
});
export const EventSchema = z.object({
  id: z.string(), sequence: z.number(), time: z.string(), type: z.string(),
  actor: z.string(), detail: z.string(), status: z.string(), spanId: z.string(),
});
export const RunSchema = z.object({
  id: z.string(), subject: z.string(), startedAt: z.string(), status: z.enum(['running','success', 'review', 'failed']),
  decision: z.string(), latency: z.number(), tokens: z.number().nullable(), cost: z.number().nullable(),
  releaseId: z.string(), plan: z.array(z.string()), spans: z.array(SpanSchema), events: z.array(EventSchema),
});
export const ExperimentSchema = z.object({
  id: z.string(), name: z.string(), releaseId: z.string(), dataset: z.string(), datasetVersion: z.string(),
  evaluatorVersion: z.string(), count: z.number(), status: z.enum(['passed', 'regression', 'pending']),
  metrics: z.array(z.object({key:z.string(), label:z.string(), baseline:z.number().nullable(), candidate:z.number().nullable(), threshold:z.number()})),
  failures: z.array(z.object({id:z.string(), subject:z.string(), agent:z.string(), expected:z.string(), actual:z.string(), score:z.number().nullable()})),
});
export const GateSchema = z.object({id:z.string(), name:z.string(), status:z.enum(['PASS','FAIL','UNKNOWN']), evidence:z.string(), threshold:z.string()});
export const ReleaseSchema = z.object({
  id:z.string(), version:z.string(), state:z.enum(['candidate','approved','promoted','baseline']),
  decision:z.enum(['READY_FOR_APPROVAL','IMPROVE_REQUIRED','DEBUG_REQUIRED','HOLD']),
  createdAt:z.string(), commit:z.string(), dataset:z.string(), evaluator:z.string(),
  gates:z.array(GateSchema),
});
export const SnapshotSchema = z.object({
  schemaVersion:z.literal('console.v1'), environment:z.literal('staging'), generatedAt:z.string(),
  demoScenario:z.string().optional(),
  metrics:z.object({executions:z.number(), successes:z.number(), avgLatency:z.number().nullable(), p95:z.number().nullable(), tokens:z.number().nullable(), cost:z.number().nullable(), coverage:z.number().nullable()}),
  trend:z.array(z.object({time:z.string(), executions:z.number(), tokens:z.number(), latency:z.number(), cost:z.number()})),
  agents:z.array(AgentSchema), mails:z.array(MailSchema), runs:z.array(RunSchema),
  experiments:z.array(ExperimentSchema), releases:z.array(ReleaseSchema),
  health:z.array(z.object({id:z.string(), label:z.string(), status:z.enum(['HEALTHY','DEGRADED','UNHEALTHY','UNKNOWN']),value:z.string(),target:z.string()})),
  incidents:z.array(z.object({id:z.string(),title:z.string(),severity:z.enum(['warning','critical']),agent:z.string(),cause:z.string(),evidence:z.array(z.string()),action:z.string(),runId:z.string()})),
  dependencies:z.array(z.object({id:z.string(),name:z.string(),status:z.enum(['ready','unknown']),description:z.string(),checkedAt:z.string()})),
  capabilities:z.object({phase:z.number(),input:z.string(),modelMode:z.string(),realMailExport:z.boolean(),gmailDraftWrite:z.boolean(),automaticMail:z.boolean().optional(),economyProfile:z.boolean().optional()}).optional(),
});
export type Snapshot = z.infer<typeof SnapshotSchema>;
export type Mail = z.infer<typeof MailSchema>;
export type Agent = z.infer<typeof AgentSchema>;
export type Run = z.infer<typeof RunSchema>;
export type Span = z.infer<typeof SpanSchema>;
export type Release = z.infer<typeof ReleaseSchema>;
export type ReviewAction = 'approve' | 'reject';
export const DecisionResponseSchema=z.object({id:z.string(),status:z.enum(['draft_saved','rejected','reviewed']),draftId:z.string().nullable()});
export const RunResponseSchema=z.object({id:z.string()});
export const CaseDetailSchema=z.object({
  id:z.string(),experimentId:z.string(),input:z.string(),reference:z.string(),baselineOutput:z.string(),candidateOutput:z.string(),
  rubric:z.array(z.object({criterion:z.string(),score:z.number(),reason:z.string()})),evaluator:z.string(),dataset:z.string(),promptBefore:z.string(),promptAfter:z.string(),
});
export const ManifestSchema=z.object({releaseId:z.string(),graph:z.string(),policy:z.string(),priceSnapshot:z.string(),agents:z.array(z.object({id:z.string(),version:z.string(),prompt:z.string(),model:z.string()}))});
export const ReleaseEvidenceSchema=z.object({releaseId:z.string(),window:z.string(),experiment:ExperimentSchema.nullable(),metrics:z.object({executions:z.number(),successes:z.number(),p95:z.number().nullable(),tokens:z.number().nullable(),cost:z.number().nullable(),coverage:z.number().nullable()}),diagnosis:z.object({quality:z.number().nullable(),status:z.enum(['HEALTHY','DEGRADED','UNHEALTHY','UNKNOWN']),hypothesis:z.string(),evidence:z.array(z.string()),nextAction:z.string()})});

# Memory integration contract

Updated: 2026-11-27. Status: proposed runtime contract; step 1 documentation complete.

This proposal defines ownership, identity, evidence, freshness, and acknowledgment rules for the [working-memory and world-knowledge refactor](../reports/working-memory-world-knowledge-refactor-2026-11-27.md). It replaces the earlier snapshot-centered memory proposal. It does not implement runtime guards or change service contracts.

For this refactor, these boundaries supersede conflicting memory ownership and persistence assumptions in the older [GameplayEngine](GameplayEngine.md), [Strategy](Strategy.md), and [Goal](Goal.md) proposals. Those documents retain independent feature ideas; they are not descriptions of current behavior. The [reference documents](../reference/Architecture.md) change when the corresponding implementation lands.

## Ownership

| Information | Authoritative owner | Representation and lifetime |
| --- | --- | --- |
| Current location, occupants, vitals, combat, possessions, and equipment | WorkingMemory | Confirmed session observations; invalidated by relevant evidence or a new connection |
| Goal progress, pending action, tried exits, consider freshness, conversations | WorkingMemory | Session state; checkpointed independently of knowledge handoff |
| Evidence awaiting transfer | WorkingMemory | Ordered pending observations retained until acknowledged |
| Learned command descriptions, help, explored map, historical encounters, gear sources | Player-scoped KM knowledge after acceptance | Retained evidence; historical location and availability remain historical |
| Bootstrap knowledge before KM acceptance | Pending evidence and local WorldKnowledge view | Usable within its documented scope; not yet retained knowledge |
| Knowledge facts read from KM | WorldKnowledge | Typed local cache with identity, provenance, and validity metadata |
| Routes, target choices, aggression assessments, gear strategies | KM request conclusions | Typed results cached by WorldKnowledge for their input revision and request |
| Hypothetical outcomes | KM projections | Never installed as confirmed session state |

GameplayEngine orchestrates observation, synchronization, inference, command validation, execution, and feedback. It does not own a second session clock or presence list. Parsers live in the play layer; transport remains in src/net. Domain objects enforce their invariants without opening sockets or acquiring service clients.

One command value type and ordered collection express shared command rules. Learned descriptions belong to knowledge; current availability belongs to the session. Help topics and category inference never establish availability. Execution retains the runtime's safety and availability checks.

The old REST documents remain compatibility boundaries. Sending new fields does not establish that a service retains them. SOMDB.Memories.json remains a fixture. The memory operator command remains a review operation, not a transfer acknowledgment.

## Session identity

The following proposed value is the immutable gameplay-session identity envelope. Internal fields use snake_case; adapters normalize service fields at the boundary. This specifies a runtime contract, not additions to existing REST schemas.

| Field | Source and rule |
| --- | --- |
| agent_id | Agent document ID when present; absence is explicit, never fabricated |
| agent_name | Required enabled agent selected by registry lookup; current memory API key |
| account_id | Required AuthResponse.id from successful authentication |
| account_name | Authenticated name, checked against the configured agent account |
| character_id | Required ID of the selected authenticated character-list entry |
| character_name | Selected authenticated character name, checked against the agent character |
| km_player_name | Existing KmPlayer identity derived from configured account/character spellings |
| world_key | Deployment scope derived from normalized auth origin and effective telnet host/port; retained with checkpoints |
| session_id | New random UUID per successfully established game login; unchanged by idle/play or forced bootstrap |

IDs are opaque exact-match strings. Agent lookup and account/character name comparison follow existing case-insensitive lookup behavior. Do not lowercase IDs or the KM situation name. The configured agent spelling continues to produce km_player_name, preserving the existing case-sensitive identity. Encode non-ASCII-alphanumeric UTF-8 bytes as _xx, as KmPlayer already does. Configuration spelling changes do not silently rename or merge situations.

The agent document ID, when present, and agent name must both match a checkpoint. Changed IDs or names require explicit migration. Legacy documents lacking the envelope follow the migration rules below.

Current player route names contain account and character names but no world namespace. This iteration assumes one game world per KM deployment. world_key prevents local cross-deployment checkpoint reuse; it does not isolate two worlds in the same remote situation. Multiworld sharing and renamed/recreated characters require explicit migration or separately scoped service deployments. Endpoint aliases are not automatically recognized as the same world.

### Binding and lifecycle

1. Startup may ensure the configured KM situation exists, preserving the current check. This does not authorize gameplay evidence transfer before login identity validation.
2. After authentication, require the authenticated account to match the agent account. Resolve the configured character from that account's returned character list and require the actual selected ID/name to match it. Blank IDs, unavailable characters, and different accounts or characters prevent binding.
3. Once game login reaches the playing prompt, create the session envelope. Bootstrap observations, engine state, handoff, queries, and checkpoints carry it. Pre-binding login output may be buffered only for this connection and cannot be submitted before binding succeeds.
4. Before acting, submitting evidence, applying an inference result, or restoring live state, require the active account/character/connection to match the bound envelope. Connection replacement suspends these operations and invalidates the old engine's authority.
5. Idle/play and forced bootstrap keep the session. Disconnect or new logon ends it. Reconnecting even the same character creates a new session and invalidates current-presence and tactical freshness claims.
6. Keep unacknowledged old-session evidence under its original identity. A later matching character may retry it as historical evidence; it never becomes the new session's current observation. An incompatible identity cannot submit or relabel it.

A mismatch is a reported failure with no gameplay action or knowledge mutation for the mismatched session. The operator may correct the connection and retry binding. Do not switch the agent document identity to accommodate another login. Credentials, JWTs, and authorization headers are excluded from envelopes, checkpoints, and diagnostics.

## Evidence envelope and ordering

An observation records what was received, what was extracted, and where the interpretation came from.

| Field | Meaning |
| --- | --- |
| session_identity | Bound envelope, including session_id |
| sequence | Positive integer allocated once in receive/fold order within the session |
| observation_id | Stable session_id plus sequence; unchanged on retry |
| observed_at | UTC receive timestamp; provenance, not an ordering authority |
| source | server for game observations; model for extracted/enriched interpretation |
| kind | Typed category such as room, command availability, score, consider, action result |
| subject_id | Stable subject identity where established; provisional encounter/visit ID where unresolved |
| payload | Typed observed fields with explicit unknown/empty distinctions |
| source_observation_ids | Supporting observations; required for model enrichment |
| action_id | Optional link to the pending command whose result is observed |

Allocate sequence numbers on the drive thread. Multiple observations from one response follow deterministic parser order. A later model result receives its own sequence and references its source observations. Clock adjustments do not reorder evidence. Checkpoint restoration preserves observation IDs and sequence numbers; a new login uses a new session ID and sequence space.

Sequence order establishes the latest observation of the same field in one session. It does not establish entity identity or automatically reconcile inconsistent sources. Delayed enrichment is no fresher than its underlying source and cannot overwrite newer server evidence merely because it completed later. Cross-session history is not a total order based only on timestamps. Historical retry must not replace active-session current facts.

Room, exit, encounter, and gear identities must not derive solely from display names. Directed exit destinations require observed movement results; reverse connections are not inferred. Unknown classifications and experience attribution remain unknown until supported. Detailed reconciliation is step 3.

## Observation semantics and freshness

Omission means no new information. An explicit empty collection means a complete observation found no members. Explicit false means observed negative evidence. Unknown is separate from false, zero, or an empty collection.

A complete room observation replaces current occupants and exits. Historical sightings remain separate. Incomplete pages cannot clear unobserved fields. A listed area is not explored. A remembered mobile location is not current presence. Sending a command does not confirm success.

Each accepted state change increments a local evidence_revision. Query context also includes the active goal/configuration revision. Relevant revisions change before a consumer can use an earlier answer. Initially, invalidating all decision results on any evidence change is acceptable; narrower dependency tracking is an optimization requiring equivalent correctness.

| Claim or result | Validity rule |
| --- | --- |
| Current occupants and exits | Latest complete observation for this visit; movement or connection replacement invalidates them until observed again |
| Consider outlook for action selection | Confirmed for this encounter and visit; relevant combat/state changes or a new visit invalidate it |
| Command availability | Observed for this character/session; refresh can remove entries; historical help cannot fill gaps |
| Equipment and purse | Latest confirmation; attempted changes make affected fields stale pending confirmation |
| Historical map or encounter | Retained provenance; informs investigation but does not establish current presence or access |
| KM conclusion | Matches session, goal/configuration, synchronized evidence revision, and fresh request identity |

Create fresh goal, progress, view, reading, route, aggression, and regear request frames when inputs change. Replacing facts does not automatically invalidate cached request conclusions. Use replacement semantics for changing N-to-1 facts and ordered sequences. Retraction of a now-unknown fact requires an adapter operation verified against KM; omission from a later assertion must not be assumed to clear it.

WorldKnowledge results retain request identity, input revision, origin, and status. Preserve nil, supported empty sequences, incomplete inputs, blocked plans, and completion as distinct outcomes. Proposed routes and final gear projections never write confirmed location or ownership into WorkingMemory.

## Handoff and acknowledgment

Periodic offload transfers evidence while WorkingMemory retains the live state needed for play. A pending observation is removable only after all its required mappings succeed. Unsupported evidence, such as conversations without an agreed KM mapping, remains local and explicitly outside the KM acknowledgment range.

| State | Required evidence | What it permits |
| --- | --- | --- |
| Pending | Observation recorded locally | Retry; local use according to freshness |
| Accepted by KM | Required expressions succeed without reasoning errors | Query against the completed synchronized input set |
| Saved by KM | Player-save response succeeds after the relevant accepted work | Record that an external snapshot was saved |
| Recoverable | Checkpoint and service restoration verified for this identity | Claim recovery only to the verified boundary |

HTTP success is insufficient when the KM result reports errors. Assertion timeout has an unknown outcome and remains retryable. Retained service memory is not a durable-save acknowledgment. Durable export does not prove restart reloads it.

Track acceptance per observation and save coverage separately. A high-water mark advances only across a contiguous acknowledged prefix of selected transferable observations; later success cannot hide earlier failure. Acknowledgment never changes identity. Compact only acknowledged pending evidence, preserving required live state and provenance.

The service commits each expression independently. A batch spanning requests is not atomic. Use deterministic subject IDs and idempotent replacement operations, remember completed mappings, and retry incomplete work. Lost acknowledgments may cause replay; replay must converge to the same indexed facts. Do not claim exactly-once delivery or remote batch deduplication.

The runtime is the single writer for its active player situation during this workflow. Serialize its handoff, query, and save operations on the drive lifecycle. Partial synchronization suspends dependent decisions until repair completes. Local emergency handling remains available from fresh session facts. Concurrent runtimes for the same player require a separate ownership contract; the API supplies no runtime lease.

Before a knowledge-dependent query, synchronize relevant pending transferable evidence even if the periodic timer has not expired. Project current tactical state through fresh frames. Baseline queries cannot see retained player assertions. A new session cannot trust an old conclusion by reusing its frame name.

On idle or shutdown, attempt bounded handoff and save without gameplay commands. Failed work remains pending and is reported. Cadence, batch limits, retry delay, and retention are ordinary agent tuning once the agent document supports them; this contract does not silently add companion-service fields.

## Persistence and migration boundaries

Separate session checkpointing from knowledge persistence. The checkpoint eventually carries identity, state and sequence revisions, pending evidence, mapping acknowledgments, and durable-save coverage. Version its representation. Select runtime-owned storage in step 11; current modulith schemas cannot round-trip these sections.

The existing memory API is keyed by agent name and the knowledge API by character ID. Those paths do not establish the full envelope. Preserve supported bodies through adapters. Do not assume extra fields survive. Do not modify companion schemas or add a live Mongo client in this iteration.

Legacy documents without identity metadata are migration input. After a matching live login, supported content may seed historical knowledge or provisional descriptions. It cannot restore confirmed presence, combat, command availability, or equipment. Do not fabricate pending work from an old snapshot.

Reject an enriched checkpoint with a different world, agent, account, or character identity without submitting or overwriting it. A same-character old-session checkpoint restores pending historical work and compatible progress only; refresh live observations. Changed goal kind/target invalidates incompatible progress; changed risk constrains subsequent decisions. Renamed or recreated accounts/characters require explicit migration rather than reuse by name.

The NLP service supports explicit player export but does not automatically reload exports at restart. Without verified restoration or replay, report knowledge recovery as unavailable. Keep accepted-but-not-durably-covered evidence recoverable locally when crash recovery is implemented. Save failure cannot clear pending evidence; resetting a shared KM situation is not a recovery shortcut.

## Acceptance scenarios for implementation

These are requirements for later implementation steps. They are specified here; step 1 has not implemented or run them as new tests.

| Scenario | Required result | Implementation step |
| --- | --- | --- |
| Another account or another character on the configured account logs in | Binding fails; no evidence submission or gameplay action under the configured KM player | 2–3, 6 |
| Connection changes after engine creation | Old engine/results lose authority; rebind before action or synchronization | 2–3, 8 |
| Same-character reconnect | New session ID; old pending evidence stays historical; live claims need refreshing | 2–3, 11 |
| Checkpoint has another character ID despite the same name | Reject restore/submission; preserve it for review or migration | 11–12 |
| Complete look has zero occupants or exits | Clear current membership; preserve history | 3 |
| Delayed model extraction follows a newer look | Preserve provenance; do not overwrite current facts from the older source | 3, 5–6 |
| Changed evidence is queried twice in one retained player situation | Fresh request and current result; no old cached conclusion | 8–9 |
| Third expression fails after two successes | Keep incomplete mappings pending; dependent queries wait; replay converges | 6–8 |
| Assertions succeed but player save fails | Record acceptance; do not advance durable coverage | 7, 11 |
| Historical replay follows a new live observation | Retain history without replacing newer current claims | 6–8, 11 |
| Gear strategy predicts acquisition/equipment | Possessions remain unchanged until server confirmation | 9–10 |
| Legacy memory lacks an identity envelope | Matching-login migration only; no current tactical authority | 11–12 |

## Step 1 completion boundary

Step 1 defines the contract and acceptance requirements. Runtime types, identity guards, parser changes, synchronization, persistence, and regression tests belong to later numbered report steps. Runtime behavior is unchanged by this document.

Implementation preserves authentication/telnet wire contracts, socket ownership, agent-document persona and tuning ownership, and refusal of telnet option negotiation. Behavioral classes and dataclasses gaining methods live in their own PascalCase files with from_json boundaries. No additional inheritance hierarchy, event bus, section registry, or companion repository change is required.

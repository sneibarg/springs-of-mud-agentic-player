# Evidence to Knowledge Machine

`play.KmEvidenceAdapter` builds deterministic, player-scoped assertion plans from immutable SessionEvidence. It does not submit expressions, acknowledge records, mark bootstrap complete, or save KM. The periodic handoff coordinator is step 7. The adapter is callable as:

```python
plan = KmEvidenceAdapter(player.name).plan(record, memory.session.evidence)
```

The record must belong to that journal. The adapter replays only its ordered prefix, so later room replacement, changed command metadata, or newer observations cannot change a retry plan. Invalid ordering and source references are rejected. Applied model enrichment must reference the matching server evidence type. A mapping result is an immutable EvidenceMapping with observation ID, player name, status, expressions, and unmapped reasons. It supports `from_json` for local callers.

| Status | Meaning |
| --- | --- |
| mapped | All supported mappings selected for this record produced a plan; this is not KM acceptance. |
| partial | Some expressions are available, but required facts remain unmapped; the whole record cannot be acknowledged. |
| unsupported | No submit-ready plan exists for the record. Keep it pending/local. |
| local | Source/provenance material lies outside the transfer selection. |

Malformed input produces an unsupported plan with no expressions and cannot contaminate later projection state. An invalid journal/source envelope raises ValueError. No mapping result authorizes an action or proves a live KM evaluation succeeded.

## Shared boundary

KmSyntax owns reserved-symbol handling, quoting, sequence encoding, deterministic frame identities, player-name validation, replacement forms, and the existing printed-answer unwrapping. CommandSituation and LevelQuestion reuse its encoders. Reserved words and boolean/nil constants are quoted when supplied as data, case-insensitively; strings escape quotes and backslashes and normalize embedded line breaks. New frame names encode player, type, and identity independently using UTF-8 hex. User labels never become executable KM syntax.

Every generated update uses `now-has`, including ordered sequences and explicit empty `(:seq)` values. Frames are player-scoped and calls must eventually go through that player's KmPlayer route. The builder itself does not validate an authenticated game account/character/connection envelope; the transport lifecycle still needs that guard. No shared global assertions or REST calls occur during planning.

## Mapping rules

| Evidence | Existing vocabulary and replacement behavior |
| --- | --- |
| commands, help, applied command/category enrichment | Som-Known-Command descriptions; `som-known-command` indexes the latest server availability in server order. Metadata-only commands never join that index. Immutable commands evidence captures restored descriptions. |
| listed_areas | Som-Area name, author, and numeric low/high range; `som-area` replaces the ordered listing, including empty. Listing never sets `som-explored`. Non-numeric ranges remain explicit partial mappings. |
| complete room | ID-addressed Som-Explored-Room and Som-Room-Exit; accumulated `som-explored-room` history and replacement `som-room-exit` order. Same-title rooms stay distinct. Inactive exits leave the active sequence. |
| captured beings | Som-Mobile encounter identities and ordered `som-known-mobile` history; explicit player/nonplayer classification, observed aggression, and last observed explored room. Disappearance does not erase history. |
| captured tactical context | Observation-specific Som-Mobile-Reading frames and a Som-Goal-View containing `som-reading`. Only current beings are projected; fresh outlook requires both the captured visit marker and captured encounter consider. A stale reading has no outlook. Empty current presence produces an empty reading sequence. |
| gear_state | Explicit confirmed inventory/equipment/purse snapshot mapped to Som-Gear-State and `som-gear-state`. No prediction or display sighting can confirm it. |
| gear_sources | Explicit complete opportunity snapshot mapped to Som-Gear-Source, Som-Gear-Piece, and `som-known-gear-source`; unknown flags do not authorize access/acquisition. |

ObservationPipeline captures movement-origin room updates after confirmed arrival/refusal, as well as current beings and fresh consider outlooks, so the adapter does not need mutable WorkingMemory to reconstruct a historical response. A complete look establishes an explored room. Historical snapshots alone cannot establish another explored room. Only an observed directed edge can supply a destination; reverse connections and room-area membership are never inferred from labels.

The KM route contract treats missing door flags as no required step. Runtime `None` means unknown. Therefore a destination is withheld from the routable exit until the destination room is observed and both open/unlock prerequisites are explicitly assessed. Such a known destination with unknown prerequisites is a partial mapping, with its reason retained. Direction and known flags remain expressible; false is distinct from unknown. A fresh exit snapshot avoids inheriting an old destination or flag when the current assessment becomes unknown. This is a conservative contract gap, not a claim that the door is open.

Command, area, exit, tactical-reading, gear-state, and opportunity snapshot frames include observation identity where values need to become unknown or membership changes. Replacing the relevant index selects the new version while old frames remain historical. Encounter and gear-piece identity stays stable. Omitted historical encounter/piece fields supply no new information; they do not retract a prior observation. Explicit null gear assessments are rejected rather than treated as false or as a verified retraction. Retraction against an actual KM instance remains unverified.

## Explicit gear input contracts

These are adapter input contracts for future observation producers. The runtime does not yet parse inventory/equipment/shop/identify output into them. They use snake_case internally; collection schemas and fixtures gain no fields.

A `gear_state` payload has `state_id`, `confirmed: true`, complete `owned` (piece objects), complete `equipped` (owned item IDs), nonnegative integer `coins`, an observed `room_id`, and integer `level`. `alignment_side` may be good, evil, or neutral. Optional `defeated` contains concrete encounter IDs. Empty owned/equipped sequences and zero coins are explicit observations. Equipped IDs must be unique and owned. The adapter requires server observation provenance and an already explored room; model output cannot confirm ownership.

Each piece has an `item_id`. Optional supported fields are short, keyword, location, worn_slot, slot_index, description, look_result, comparison, compared_to, enchant, gear_kind, weapon_type, wield_band, object_level, level_block, alignment_known, alignment_block, rejects, and usable. Distinct item IDs with the same label stay separate, including paired slots. Numeric/boolean fields are validated; unknown/null is never changed to zero or false. Unsupported piece fields reject the record instead of being silently dropped.

A `gear_sources` payload contains a complete ordered `sources` list, including an explicit empty list to revoke all indexed sources. Each source has `source_id`, kind (room/shop/corpse/mobile/player), an item object, observed `room_id`, and `holder_id` for non-room sources. Optional fields are price, available, permitted, accessible, requires (piece IDs), loot_known, model_known, assessed_level, risk, and yields (piece IDs). A declared loot bundle must include the offered piece. Price/assessed level are nonnegative integers; flags must be actual booleans. Missing access, permission, loot, or combat assessments remain missing. New opportunity versions cannot inherit old affirmative flags. Shop/mobile/player holders reference concrete encounter identities; no sighting invents nonplayer classification or a loot/combat model.

Raw room objects and model description items are not automatically gear opportunities. They do not establish gear type, usable keywords, possession, permission, price, accessibility, or loot. Unsupported enrichment remains available locally for later observation work.

## Remaining integration boundaries

Roster (`players`) evidence has no agreed roster index in this component vocabulary and stays unsupported; who is not a room encounter. Score/progress and generic combat fields await the inference projection work rather than being invented as historical mobile facts. Conversations, unapplied model output, and unknown evidence kinds gain no fabricated mapping. Applied room-item enrichment still needs a suitable item/observation contract.

These gaps keep the corresponding evidence pending, and bootstrap cannot claim full acceptance while its required roster/other records lack mappings. Step 7 must honor mapping status and check every required KM result before acknowledgment. Step 8 connects fresh inference requests to synchronized inputs. Live route/retraction evaluations, actual gear observation producers, authenticated session binding, periodic transfer, and durable checkpoints remain separate work. No companion service or KM library source was changed.

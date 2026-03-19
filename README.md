# multi-rag-agent-orchestrator-example
an experiment to write down my AI agents in future

# Showcase

![image](./main.png)

```mermaid
flowchart LR
    U["Customer Request"] --> O["OrchestratorAgent\nResponsibility: sequence stages and pass structured state"]

    O -->|"raw_request"| RA1
    subgraph RA["RequestAnalysisAgent\nResponsibility: extract metadata, items, and catalog matches"]
        RA1["analyze_request_metadata_tool\nPurpose: validate request metadata\nHelpers: update_workflow_context"]
        RA2["parse_request_items_tool\nPurpose: structure item lines from the request\nHelpers: parse_request_items_from_text"]
        RA3["normalize_request_items_tool\nPurpose: map parsed items to supported catalog items\nHelpers: normalize_request_items, resolve_catalog_item, convert_item_quantity"]
        RA1 -->|"metadata"| RA2
        RA2 -->|"parsed_items"| RA3
    end
    RA1 -->|"request_metadata, request_profile, dates"| O
    RA2 -->|"parsed_items"| O
    RA3 -->|"normalized_items, unsupported_items, ambiguous_items"| O

    O -->|"normalized_items, request_date, delivery_deadline"| IR1
    subgraph IR["InventoryRetrievalAgent\nResponsibility: check stock and prepare reorders"]
        IR1["assess_inventory_tool\nPurpose: compute availability, shortages, and feasibility\nHelpers: get_stock_level, get_supplier_delivery_date"]
        IR2["build_reorder_plan_tool\nPurpose: convert shortages into reorder actions\nHelpers: direct tool logic from inventory_result"]
        IR1 -->|"inventory_result"| IR2
    end
    IR1 -->|"inventory_result"| O
    IR2 -->|"reorder_plan"| O

    O -->|"normalized_items, request_profile"| QR1
    subgraph QR["QuoteRetrievalAgent\nResponsibility: retrieve pricing context and generate quote"]
        QR1["retrieve_similar_quotes_tool\nPurpose: find relevant historical quotes\nHelpers: search_quote_history"]
        QR2["generate_quote_tool\nPurpose: compute quote totals, discount, and pricing notes\nHelpers: direct tool logic using catalog prices"]
        QR1 -->|"similar_quotes"| QR2
    end
    QR1 -->|"similar_quotes"| O
    QR2 -->|"quote_result"| O

    O -->|"normalized_items, unsupported_items, ambiguous_items, inventory_result, reorder_plan, quote_result"| SF1
    subgraph SF["SynthesisFulfillmentAgent\nResponsibility: decide outcome and persist results"]
        SF1["finalize_decision_tool\nPurpose: choose approved_full, approved_partial, delayed, or declined\nHelpers: direct tool logic on validated stage outputs"]
        SF2["write_transactions_tool\nPurpose: write approved sales and stock-order transactions\nHelpers: create_transaction"]
        SF3["log_request_memory_tool\nPurpose: store completed request outcome in long memory\nHelpers: direct database write to request_memory"]
        SF1 -->|"decision, quote_total, notes"| SF2
        SF1 -->|"decision, quote_total, delivery_feasible, notes"| SF3
    end
    SF1 -->|"final_decision"| O
    SF2 -->|"transaction_summary"| O
    SF3 -->|"memory_log_summary"| O

    O -->|"decision, quote total, notes"| R["Customer-Facing Result"]

```


# Flowchart Explanation

## Customer request enters the orchestrator

The OrchestratorAgent is the top-level controller. It creates a fresh request state, resets workflow context, chooses the display mode (showcase, debug, or quiet), and runs the request through analysis, inventory, quote, and synthesis in order.

## Request analysis begins
The RequestAnalysisAgent is responsible for understanding the request. It does not directly mutate the business state; instead, it calls tools that validate and structure what it inferred.

### Metadata extraction

analyze_request_metadata_tool validates request-level fields such as intent, urgency, request_date, delivery_deadline, and the request_profile fields like job_type, order_size, event_type, and mood. It also stores these values in workflow context so later tools can recover even if the agent omits arguments.

### Parsed item extraction
parse_request_items_tool validates item rows like raw_name, quantity, and unit. If the agent fails to pass items, it can reconstruct them from the raw request text using the helper parsing pipeline.

### Normalization into the supported catalog
normalize_request_items_tool is the catalog-matching step. In the current design, the agent is allowed to call it with {}, and the tool reads parsed items from workflow context, then runs normalize_request_items(...).

#### How normalization works internally

For each parsed item:

`resolve_catalog_item(...)` tries alias memory first.
Then it uses embedding similarity as the primary signal against the supported catalog.
Lexical scoring and keyword heuristics act as support and tie-breakers.
The result is classified as `SUPPORTED`, `UNSUPPORTED`, or `AMBIGUOUS`.

#### Quantity normalization

If an item is supported, `convert_item_quantity(...)` converts units like reams into normalized internal units such as sheets. This ensures inventory and quoting operate on a consistent quantity system.

Request analysis output
The result of stage 1 is a validated split into:

```
normalized_items
unsupported_items
ambiguous_items
```

## Inventory stage starts

The `InventoryRetrievalAgent` checks whether supported items can actually be fulfilled. Like normalization, it can rely on workflow context, so assess_inventory_tool can work even if the agent omits the items argument.

### Inventory assessment

`assess_inventory_tool` looks up current stock for each supported normalized item, calculates:

```
available
shortage
needs_reorder
estimated_delivery
feasible
```
It uses `get_stock_level(...)`, and `get_supplier_delivery_date(...)` to estimate replenishment timing.

### Reorder planning

`build_reorder_plan_tool` converts shortages into structured reorder actions. If an item is short, this stage generates the quantity to order and the expected supplier delivery date.

## Quote stage starts

The `QuoteRetrievalAgent` handles pricing. It does not decide approval; it only finds relevant historical context and computes a quote.

### Historical quote retrieval

`retrieve_similar_quotes_tool` searches quote history using normalized item names plus request metadata. This gives the pricing engine historical examples without changing catalog truth.

### Quote generation

`generate_quote_tool` computes:

```
base_total from current catalog prices
optional discount behavior using historical context
final_total
pricing notes and explanation
```

## Synthesis stage starts
The SynthesisFulfillmentAgent combines all prior results. It receives normalized items, unsupported/ambiguous items, inventory results, reorder plan, and quote result.

## Final decision

`finalize_decision_tool` decides whether the request is:

```
approved_full
approved_partial
delayed
declined
```

This decision is based on supportability, ambiguity, inventory feasibility, and pricing.

## Transaction writing

`write_transactions_tool` writes approved sales transactions and approved reorder transactions into the database. This is where the workflow becomes operational, not just analytical.


## Long-memory logging

`log_request_memory_tool` stores the completed request outcome in persistent memory. That includes the original request, profile, normalized items, unsupported items, decision, quote total, delivery feasibility, and notes.

## Customer-facing response

After synthesis, the orchestrator formats the final plain-text result with `build_decision_response(...)`. In `showcase` mode, `WorkflowShowcase` renders the live dashboard; in `debug` mode, raw agent traces are shown; in `quiet` mode, only the final result is returned.

## Safety rails around the whole flow

Three important support systems sit around the main pipeline:

* Pydantic schema hardening ensures tool inputs/outputs are valid.
* Workflow context priming lets empty or partial tool calls recover safely.
* `_extract_tool_result(...)` and fallback logic allow the orchestrator to recover when an agent produces incomplete or malformed intermediate output.

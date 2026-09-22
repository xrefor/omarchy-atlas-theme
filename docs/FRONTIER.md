# EVE Frontier intelligence panel

The apps component includes `atlas-frontier`, a read-only terminal panel for
observing public EVE Frontier objects on Sui. It never signs a transaction,
stores a private key, or treats a wallet address as proof of authentication.
Press **Ctrl+Space, then E** in the ATLAS tmux workspace to toggle the panel.
On a wide terminal it opens beside the current pane; below 130 columns it opens
as a detached `frontier` window. Run `atlas-frontier show` outside tmux for a
normal full-window view.

## Evidence model

The panel deliberately separates two kinds of information:

- **Observed** values come from the configured chain: object type, contract
  `ONLINE`/`OFFLINE` state, version, digest, previous transaction, checkpoint,
  character address and capability custody.
- **Monitor** values are local conclusions: `UPDATED`, `UNCHANGED`, or
  `UNAVAILABLE`. The first complete observation creates a baseline and is not
  reported as a change.

Assemblies are shared Sui objects. The panel therefore reports `OwnerCap`
capabilities held by the Smart Character and the assemblies those capabilities
control; it does not call wallet-owned Sui objects "owned assemblies." See the
[Frontier ownership model](https://docs.evefrontier.com/smart-contracts/ownership-model)
and [Smart Character documentation](https://docs.evefrontier.com/smart-assemblies/smart-character).

Local history begins with the first successful complete poll. Cached observations
are never displayed as current after a failed poll. Missing, partial and invalid
responses remain `UNAVAILABLE` with a reason instead of becoming zero or a false
ownership transfer.

## Configuration

The account configuration is `~/.config/atlas/frontier.json`. It is intentionally
separate from the installer-managed `frontier-palette.json`, so theme updates do
not change account settings. Configure a public address with:

```bash
atlas-frontier configure \
  --wallet 0xYOUR_SUI_ADDRESS \
  --endpoint https://graphql.testnet.sui.io/graphql \
  --published-package 0xPUBLISHED_WORLD_PACKAGE_ID \
  --type-origin 0xWORLD_DEFINING_ID \
  --environment "Stillness (user configured)" \
  --watch 0xASSEMBLY_ID="Home node"
```

Configuration probes and records the endpoint's chain identifier. Later chain
mismatches stop collection before any account or assembly claim is made.
`--published-package` is the exact current package object to probe for required
Frontier modules. `--type-origin` is the per-struct defining ID used in
Move type names. Sui package upgrades can make those IDs different, so ATLAS
never substitutes one for the other. Configuration verifies every supplied
defining ID against the published package's on-chain `typeOrigins`. One bare
type-origin ID applies to all known Frontier structs; environments with split origins can instead repeat
`--type-origin NAME=DEFINING_ID` for `PlayerProfile`, `Character`, `OwnerCap`,
`Assembly`, `Gate`, `StorageUnit`, and `NetworkNode`.

Add an exact
coin type with `--eve-coin-type` only after confirming it for that environment;
the monitor never discovers an EVE coin by its symbol.

`--watch` accepts additional public Frontier assembly objects (Assembly, Gate,
Storage Unit or Network Node). Other public object schemas are intentionally not
decoded as assemblies.

If address changes or multiple historical `PlayerProfile` objects make discovery
ambiguous, provide the exact Smart Character with `--character`. Its on-chain
`character_address` must still match the monitored wallet or collection stops.

The [Frontier Resources page](https://docs.evefrontier.com/tools/resources)
publishes environment package information. Confirm the published package object
ID for that environment, then obtain each struct's defining ID from the package's
on-chain `typeOrigins`; those values and the contract
repository are evolving and are not baked into ATLAS as timeless or canonical.
The label entered with `--environment` is always shown as user-configured.
Supplying `--expected-chain` from an independently trusted source is stronger
than accepting the identifier reported by the configured endpoint itself.

Only HTTPS endpoints are accepted, except loopback HTTP endpoints used for local
testing. URLs containing credentials or query strings are rejected. Configuration
containing token, secret or private-key fields is rejected. The normal monitor
uses only public GraphQL reads.

Useful commands:

```bash
atlas-frontier status
atlas-frontier show
atlas-frontier toggle --pane "$TMUX_PANE"
atlas-frontier configure --help
```

## Data and controls

The overview shows a matched on-chain Smart Character address binding, tribe ID, capability and
controlled-assembly counts, optional exact-type EVE balance, watched assemblies,
recent locally observed changes, chain identity and checkpoint provenance.
Infrastructure and activity pages retain object/capability identifiers and the
local evidence timeline.

| Key | Action |
| --- | --- |
| `1` | Overview |
| `2` | Infrastructure and provenance |
| `3` | Local change history |
| `↑` / `↓`, `j` / `k` | Scroll |
| `r` | Request a coalesced refresh |
| `q` / Escape | Close the panel; collection stops |

The default poll interval is 15 seconds. Requests are bounded and paginated;
rate limits and partial pagination are reported rather than hidden. HTTP 429
responses honor a bounded `Retry-After` value and use exponential backoff with
jitter. The panel
uses polling because it is the supported conservative baseline. Frontier's
[read-path documentation](https://docs.evefrontier.com/tools/interfacing-with-the-eve-frontier-world)
also describes gRPC streaming for higher-throughput applications, which this
personal panel does not require.

## Limits

- The official Resources, World Upgrades and current contract repository can
  temporarily disagree about environment/package status. ATLAS verifies the
  configured chain, published package modules and their on-chain type origins,
  but cannot declare which deployment is game-authoritative.
- LUX and other private/off-chain account data are not available from public Sui
  reads. Cleartext location is intentionally not inferred from its on-chain hash.
- EVE Vault aliases authorize an account; they are not alternate asset addresses.
  Configure the account address recorded by the Smart Character.
- A previous transaction produced the displayed object version; it is not
  automatically an ownership-transfer event.
- Indexer visibility can lag transaction finality. Retrieval age, checkpoint age
  and last-object-change time are displayed as distinct concepts.
- Semantic decoding fails closed for unknown or upgraded object shapes. Generic
  object provenance remains available where possible.

State is stored beneath `${XDG_STATE_HOME:-~/.local/state}/atlas/` using a
namespace derived from chain, wallet, resolved Smart Character, published package
IDs, defining type origins and configured coin type.
Changing that identity creates a new baseline instead of false update alerts.
Remove `~/.config/atlas/frontier.json` and
`${XDG_STATE_HOME:-~/.local/state}/atlas/frontier.json` to forget
the public address and local observations.

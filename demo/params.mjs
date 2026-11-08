// Shared deployment parameters. Kept in its own module so importing them never runs a deploy.

export const RPC = 'https://rpc.testnet.fastnear.com';

// Identical to the set the simulation picked (see ../sim and ../contract/README.md), except the epoch
// length: 10s on the demo instance so an epoch turns over on camera. Production would use 86_400e9.
export const GENESIS_ARGS = {
  genesis: '10000000000000000000000000', // 10M GRIP at 18 decimals
  reserve_bps: 3000,
  lock_target_bps: 6000,
  burn_target_bps: 3500,
  mint_bps: 100,
  burn_bps: 200,
  early_exit_bps: 1000,
  epoch_length_ns: Number(process.env.EPOCH_NS || 10_000_000_000),
};

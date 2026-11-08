//! GRIP, a token whose supply follows how much of its live float the community keeps locked.
//!
//! The whole mechanic is one immutable rule, evaluated once per epoch by anyone:
//!
//! ```text
//! engaged      = total_supply - reserve
//! locked_share = total_locked / engaged
//!
//! locked_share >= lock_target -> mint mint_bps of supply, pro-rata to lockers
//! locked_share <= burn_target -> burn burn_bps of supply, out of the reserve only
//! otherwise                   -> nothing
//! ```
//!
//! The mint stops at `max_supply` (4x genesis). Without that ceiling a rule that pays a percentage of
//! current supply every epoch compounds without limit: at a 60 second epoch it passes u128 in about two
//! days, and because overflow checks are on, `tick` would panic and the rule would never run again.
//!
//! There is no owner mint, no pause, no setter, and no way to touch the reserve
//! except the burn rule. After `new` returns, the deployer key has no power.
//!
//! Reproduce the supply dynamics behind these parameters with `python3 sim/sim.py`.

use near_sdk::json_types::U128;
use near_sdk::store::LookupMap;
use near_sdk::{env, near, AccountId, PanicOnDefault};

const SCALE: u128 = 1_000_000_000_000; // 1e12, reward-per-locked-unit precision
const MAX_HISTORY: usize = 90;
const MAX_EPOCHS_PER_TICK: u64 = 12;
/// Concurrent lockers a single tick can expire. Locks release themselves at their deadline, so grip has
/// to be maintained rather than set once; a production contract would index expiries by epoch instead.
const MAX_LOCKERS: usize = 32;
/// Hard ceiling on supply, in multiples of genesis. 1% per epoch of the *current* supply compounds, so
/// an unbounded rule is a runaway by construction. Four genesis supplies leaves room for the sustained
/// grip case in `sim/sim.py` (1.75x) and still bounds the thing.
const MAX_SUPPLY_MULT: u128 = 4;

#[near(serializers = [borsh, json])]
#[derive(Clone, Copy)]
pub struct Lock {
    pub amount: u128,
    pub until_epoch: u64,
    pub debt: u128, // amount * acc / SCALE at last settlement
}

#[near(serializers = [borsh, json])]
#[derive(Clone)]
pub struct EpochRecord {
    pub epoch: u64,
    pub timestamp: u64,
    pub supply: U128,
    pub reserve: U128,
    pub locked: U128,
    pub share_bps: u32,
    pub action: String,
}

#[near(serializers = [borsh, json])]
#[derive(Clone)]
pub struct State {
    pub total_supply: U128,
    pub max_supply: U128,
    pub reserve: U128,
    pub engaged: U128,
    pub total_locked: U128,
    pub locked_share_bps: u32,
    pub epoch: u64,
    pub epoch_start: u64,
    pub epoch_length_ns: u64,
    pub lock_target_bps: u32,
    pub burn_target_bps: u32,
    pub mint_bps: u32,
    pub burn_bps: u32,
    pub early_exit_bps: u32,
    pub mint_epochs: u64,
    pub burn_epochs: u64,
    pub expired_locks: u64,
    pub history: Vec<EpochRecord>,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Grip {
    pub owner: AccountId,
    pub total_supply: u128,
    pub max_supply: u128,
    pub reserve: u128,
    pub balances: LookupMap<AccountId, u128>,
    pub locks: LookupMap<AccountId, Lock>,
    pub lockers: Vec<AccountId>,
    pub total_locked: u128,
    pub acc: u128,
    pub epoch: u64,
    pub epoch_start: u64,
    pub epoch_length_ns: u64,
    pub lock_target_bps: u32,
    pub burn_target_bps: u32,
    pub mint_bps: u32,
    pub burn_bps: u32,
    pub early_exit_bps: u32,
    pub mint_epochs: u64,
    pub burn_epochs: u64,
    pub expired_locks: u64,
    pub history: Vec<EpochRecord>,
}

#[near]
impl Grip {
    /// All eight parameters are fixed here and readable forever. Nothing can change them later.
    #[init]
    pub fn new(
        owner: AccountId,
        genesis: U128,
        reserve_bps: u32,
        lock_target_bps: u32,
        burn_target_bps: u32,
        mint_bps: u32,
        burn_bps: u32,
        early_exit_bps: u32,
        epoch_length_ns: u64,
    ) -> Self {
        assert!(genesis.0 > 0, "genesis must be positive");
        assert!(reserve_bps <= 10_000, "reserve_bps out of range");
        assert!(lock_target_bps <= 10_000 && burn_target_bps <= 10_000, "target out of range");
        assert!(burn_target_bps < lock_target_bps, "burn_target must be below lock_target");
        assert!(mint_bps > 0 && burn_bps > 0, "rates must be positive");
        assert!(mint_bps <= 1_000 && burn_bps <= 1_000, "rates above 10% per epoch are not allowed");
        assert!(early_exit_bps <= 5_000, "early_exit_bps above 50%");
        assert!(epoch_length_ns > 0, "epoch_length_ns must be positive");

        let reserve = genesis.0 * reserve_bps as u128 / 10_000;
        let mut balances = LookupMap::new(b"b");
        balances.insert(owner.clone(), genesis.0 - reserve);

        env::log_str(&format!(
            "EVENT_JSON:{{\"standard\":\"nep141\",\"version\":\"1.0.0\",\"event\":\"ft_mint\",\
             \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\"}}]}}",
            owner,
            genesis.0 - reserve
        ));

        Self {
            owner,
            total_supply: genesis.0,
            max_supply: genesis.0.saturating_mul(MAX_SUPPLY_MULT),
            reserve,
            balances,
            locks: LookupMap::new(b"l"),
            lockers: Vec::new(),
            total_locked: 0,
            acc: 0,
            epoch: 0,
            epoch_start: env::block_timestamp(),
            epoch_length_ns,
            lock_target_bps,
            burn_target_bps,
            mint_bps,
            burn_bps,
            early_exit_bps,
            mint_epochs: 0,
            burn_epochs: 0,
            expired_locks: 0,
            history: Vec::new(),
        }
    }

    // ---------------------------------------------------------------- NEP-141

    pub fn ft_total_supply(&self) -> U128 {
        U128(self.total_supply)
    }

    /// Unlocked balance including rewards earned but not yet settled, so a holder can spend what they
    /// have already earned without an extra transaction.
    pub fn ft_balance_of(&self, account_id: AccountId) -> U128 {
        U128(self.balance_of(&account_id) + self.pending(&account_id))
    }

    /// Earned, not yet settled. Settling happens on the next lock, unlock or transfer.
    pub fn pending_of(&self, account_id: AccountId) -> u128 {
        self.pending(&account_id)
    }

    pub fn ft_metadata(&self) -> String {
        String::from(
            r#"{"spec":"ft-1.0.0","name":"GRIP","symbol":"GRIP","decimals":18,"icon":null}"#,
        )
    }

    #[payable]
    pub fn ft_transfer(&mut self, receiver_id: AccountId, amount: U128) {
        let sender = env::predecessor_account_id();
        assert_ne!(sender, receiver_id, "self transfer");
        self.settle(&sender);
        let from = self.balance_of(&sender);
        assert!(from >= amount.0, "not enough unlocked balance");
        self.set_balance(&sender, from - amount.0);
        let to = self.balance_of(&receiver_id);
        self.set_balance(&receiver_id, to + amount.0);
        self.emit_transfer(&sender, &receiver_id, amount.0);
    }

    // ------------------------------------------------------------------ GRIP

    /// Lock `amount` for `epochs` epochs. Extends an existing lock instead of stacking.
    pub fn lock(&mut self, amount: U128, epochs: u64) {
        assert!(amount.0 > 0, "amount must be positive");
        assert!(epochs >= 1 && epochs <= 30, "epochs must be 1..=30");
        let who = env::predecessor_account_id();
        self.settle(&who);

        let free = self.balance_of(&who);
        assert!(free >= amount.0, "not enough unlocked balance");
        self.set_balance(&who, free - amount.0);

        let mut l = self.locks.get(&who).copied().unwrap_or(Lock { amount: 0, until_epoch: 0, debt: 0 });
        if l.amount == 0 {
            assert!(self.lockers.len() < MAX_LOCKERS, "too many concurrent lockers");
            self.lockers.push(who.clone());
        }
        let until = core::cmp::max(l.until_epoch, self.epoch + epochs);
        l.amount += amount.0;
        l.until_epoch = until;
        l.debt = l.amount * self.acc / SCALE;
        self.locks.insert(who.clone(), l);
        self.total_locked += amount.0;

        env::log_str(&format!(
            "EVENT_JSON:{{\"standard\":\"grip\",\"version\":\"1.0.0\",\"event\":\"lock\",\
             \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\",\"until_epoch\":{}}}]}}",
            who, amount.0, until
        ));
    }

    /// Release a lock before its deadline and `early_exit_bps` of it is burned. After the deadline the
    /// tick has already released it, so this is a no-op.
    pub fn unlock(&mut self) {
        let who = env::predecessor_account_id();
        self.settle(&who);
        let Some(l) = self.locks.get(&who).copied() else {
            env::log_str(&format!(
                "EVENT_JSON:{{\"standard\":\"grip\",\"version\":\"1.0.0\",\"event\":\"unlock_noop\",\
                 \"data\":[{{\"account_id\":\"{}\"}}]}}",
                who
            ));
            return;
        };
        assert!(l.amount > 0, "no lock");

        let early = self.epoch < l.until_epoch;
        let penalty = if early { l.amount * self.early_exit_bps as u128 / 10_000 } else { 0 };
        let released = l.amount - penalty;

        self.locks.remove(&who);
        self.total_locked -= l.amount;
        self.total_supply -= penalty;
        self.lockers.retain(|a| a != &who);
        let free = self.balance_of(&who);
        self.set_balance(&who, free + released);

        if penalty > 0 {
            env::log_str(&format!(
                "EVENT_JSON:{{\"standard\":\"nep141\",\"version\":\"1.0.0\",\"event\":\"ft_burn\",\
                 \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\"}}]}}",
                who, penalty
            ));
        }
        env::log_str(&format!(
            "EVENT_JSON:{{\"standard\":\"grip\",\"version\":\"1.0.0\",\"event\":\"unlock\",\
             \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\",\"penalty\":\"{}\"}}]}}",
            who, released, penalty
        ));
    }

    /// Anyone can roll the epoch forward once its time is up. No keeper privilege exists.
    pub fn tick(&mut self) {
        let now = env::block_timestamp();
        assert!(
            now >= self.epoch_start + self.epoch_length_ns,
            "epoch not finished yet"
        );
        let mut rolled = 0u64;
        while now >= self.epoch_start + self.epoch_length_ns && rolled < MAX_EPOCHS_PER_TICK {
            self.epoch += 1;
            self.epoch_start += self.epoch_length_ns;
            // Locks that reached their deadline stop counting before the rule is evaluated, so grip has
            // to be maintained: an untouched lock decays into a burn epoch instead of holding the line
            // forever.
            self.expire_due_locks();
            self.apply_epoch_rule();
            rolled += 1;
        }
    }

    // ----------------------------------------------------------------- views

    pub fn get_state(&self) -> State {
        State {
            total_supply: U128(self.total_supply),
            max_supply: U128(self.max_supply),
            reserve: U128(self.reserve),
            engaged: U128(self.engaged()),
            total_locked: U128(self.total_locked),
            locked_share_bps: self.locked_share_bps(),
            epoch: self.epoch,
            epoch_start: self.epoch_start,
            epoch_length_ns: self.epoch_length_ns,
            lock_target_bps: self.lock_target_bps,
            burn_target_bps: self.burn_target_bps,
            mint_bps: self.mint_bps,
            burn_bps: self.burn_bps,
            early_exit_bps: self.early_exit_bps,
            mint_epochs: self.mint_epochs,
            burn_epochs: self.burn_epochs,
            expired_locks: self.expired_locks,
            history: self.history.clone(),
        }
    }

    /// Locked principal. Mint rewards are paid out unlocked, so this never includes them.
    pub fn locked_of(&self, account_id: AccountId) -> U128 {
        U128(self.locks.get(&account_id).map(|l| l.amount).unwrap_or(0))
    }

    pub fn until_epoch_of(&self, account_id: AccountId) -> u64 {
        self.locks.get(&account_id).map(|l| l.until_epoch).unwrap_or(0)
    }
}

impl Grip {
    fn engaged(&self) -> u128 {
        self.total_supply.saturating_sub(self.reserve)
    }

    fn locked_share_bps(&self) -> u32 {
        let engaged = self.engaged();
        if engaged == 0 {
            return 0;
        }
        ((self.total_locked.min(engaged) * 10_000) / engaged) as u32
    }

    fn pending(&self, account: &AccountId) -> u128 {
        let Some(l) = self.locks.get(account).copied() else { return 0 };
        if l.amount == 0 {
            return 0;
        }
        let entitled = l.amount * self.acc / SCALE;
        if entitled > l.debt {
            entitled - l.debt
        } else {
            0
        }
    }

    fn balance_of(&self, account: &AccountId) -> u128 {
        self.balances.get(account).copied().unwrap_or(0)
    }

    fn set_balance(&mut self, account: &AccountId, amount: u128) {
        self.balances.insert(account.clone(), amount);
    }

    /// Move a locker's share of every mint since their last touch into their unlocked balance.
    ///
    /// Rewards land in `balances`, never inside the lock. Compounding them into `l.amount` would let an
    /// unsettled locker's principal grow behind the accumulator's back, and then the pro-rata maths stops
    /// being exact: the sum of positions drifts away from `total_locked`. Paying out unlocked keeps
    /// `total_locked` equal to the sum of positions at all times, and it makes "you get paid for gripping"
    /// literal rather than self-reinforcing.
    fn settle(&mut self, account: &AccountId) {
        let Some(mut l) = self.locks.get(account).copied() else { return };
        if l.amount == 0 {
            return;
        }
        let entitled = l.amount * self.acc / SCALE;
        if entitled > l.debt {
            let owed = entitled - l.debt;
            let free = self.balance_of(account);
            self.set_balance(account, free + owed);
        }
        l.debt = l.amount * self.acc / SCALE;
        self.locks.insert(account.clone(), l);
    }

    /// Release every lock whose deadline has passed, returning the tokens to their holder unlocked.
    /// Bounded by MAX_LOCKERS, so one tick can always finish.
    fn expire_due_locks(&mut self) {
        let mut i = 0;
        while i < self.lockers.len() {
            let account = self.lockers[i].clone();
            let due = self
                .locks
                .get(&account)
                .map(|l| l.until_epoch <= self.epoch)
                .unwrap_or(true);
            if !due {
                i += 1;
                continue;
            }
            if let Some(l) = self.locks.get(&account).copied() {
                let entitled = l.amount * self.acc / SCALE;
                if entitled > l.debt {
                    let owed = entitled - l.debt;
                    let free = self.balance_of(&account);
                    self.set_balance(&account, free + owed);
                }
                let amount = l.amount;
                self.locks.remove(&account);
                self.total_locked = self.total_locked.saturating_sub(amount);
                let free = self.balance_of(&account);
                self.set_balance(&account, free + amount);
                self.expired_locks += 1;
                env::log_str(&format!(
                    "EVENT_JSON:{{\"standard\":\"grip\",\"version\":\"1.0.0\",\"event\":\"lock_expired\",\
                     \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\",\"epoch\":{}}}]}}",
                    account, amount, self.epoch
                ));
            }
            self.lockers.swap_remove(i);
        }
    }

    fn apply_epoch_rule(&mut self) {
        let share_bps = self.locked_share_bps();
        let action;

        if share_bps >= self.lock_target_bps && self.total_locked > 0 {
            let wanted = self.total_supply * self.mint_bps as u128 / 10_000;
            let room = self.max_supply.saturating_sub(self.total_supply);
            let amount = core::cmp::min(wanted, room);

            if amount == 0 {
                // The ceiling is reached. The rule still ran and still says so in the history, it just
                // cannot pay: a quiet "hold" here would hide the ceiling from anyone reading the chain.
                action = String::from("capped");
            } else {
                // The mint is paid out unlocked, so the locked principal does not change and
                // `total_locked` stays exactly equal to the sum of positions.
                self.acc += amount * SCALE / self.total_locked;
                self.total_supply += amount;
                self.mint_epochs += 1;
                action = format!("mint {}", amount);
                env::log_str(&format!(
                    "EVENT_JSON:{{\"standard\":\"grip\",\"version\":\"1.0.0\",\"event\":\"epoch_mint\",\
                     \"data\":[{{\"amount\":\"{}\",\"supply\":\"{}\",\"locked_share_bps\":{},\
                     \"lockers_amount\":\"{}\"}}]}}",
                    amount, self.total_supply, share_bps, self.total_locked
                ));
            }
        } else if share_bps <= self.burn_target_bps && self.reserve > 0 {
            let wanted = self.total_supply * self.burn_bps as u128 / 10_000;
            let amount = core::cmp::min(wanted, self.reserve);
            self.total_supply -= amount;
            self.reserve -= amount;
            self.burn_epochs += 1;
            action = format!("burn {}", amount);
            env::log_str(&format!(
                "EVENT_JSON:{{\"standard\":\"nep141\",\"version\":\"1.0.0\",\"event\":\"ft_burn\",\
                 \"data\":[{{\"account_id\":\"{}\",\"amount\":\"{}\"}}]}}",
                env::current_account_id(),
                amount
            ));
        } else {
            action = String::from("hold");
        }

        self.history.push(EpochRecord {
            epoch: self.epoch,
            timestamp: env::block_timestamp(),
            supply: U128(self.total_supply),
            reserve: U128(self.reserve),
            locked: U128(self.total_locked),
            share_bps,
            action,
        });
        if self.history.len() > MAX_HISTORY {
            self.history.remove(0);
        }
    }

    fn emit_transfer(&self, from: &AccountId, to: &AccountId, amount: u128) {
        env::log_str(&format!(
            "EVENT_JSON:{{\"standard\":\"nep141\",\"version\":\"1.0.0\",\"event\":\"ft_transfer\",\
             \"data\":[{{\"old_owner_id\":\"{}\",\"new_owner_id\":\"{}\",\"amount\":\"{}\"}}]}}",
            from, to, amount
        ));
    }
}

// ------------------------------------------------------------------- tests

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::VMContextBuilder;
    use near_sdk::testing_env;

    const GENESIS: u128 = 10_000_000 * 1_000_000_000_000_000_000; // 10M tokens, 18 decimals
    const EPOCH: u64 = 60_000_000_000; // 60s in ns
    /// Upper bound on the reward accumulator's rounding dust (0.001 token).
    const DUST: u128 = 1_000_000_000_000_000;

    fn alice() -> AccountId {
        "alice.near".parse().unwrap()
    }
    fn bob() -> AccountId {
        "bob.near".parse().unwrap()
    }

    fn ctx(predecessor: AccountId, ts: u64) {
        testing_env!(VMContextBuilder::new()
            .predecessor_account_id(predecessor)
            .current_account_id("grip.near".parse().unwrap())
            .block_timestamp(ts)
            .build());
    }

    fn deploy() -> Grip {
        ctx(alice(), 0);
        Grip::new(
            alice(),
            U128(GENESIS),
            3_000, // reserve 30%
            6_000, // mint when 60% of live float is locked
            3_500, // burn when 35% or less is locked
            100,   // 1% per mint epoch
            200,   // 2% per burn epoch
            1_000, // 10% early-exit burn
            EPOCH,
        )
    }

    #[test]
    fn genesis_splits_supply_between_owner_and_reserve() {
        let c = deploy();
        assert_eq!(c.total_supply, GENESIS);
        assert_eq!(c.reserve, GENESIS * 3 / 10);
        assert_eq!(c.ft_balance_of(alice()).0, GENESIS * 7 / 10);
        assert_eq!(c.engaged(), GENESIS * 7 / 10);
        assert_eq!(c.locked_share_bps(), 0);
        assert_eq!(c.epoch, 0);
    }

    #[test]
    fn locking_everything_mints_to_the_locker() {
        let mut c = deploy();
        ctx(alice(), 0);
        c.lock(U128(GENESIS * 7 / 10), 2);
        assert_eq!(c.locked_share_bps(), 10_000);
        assert_eq!(c.locked_of(alice()).0, GENESIS * 7 / 10);

        ctx(alice(), EPOCH);
        c.tick();
        assert_eq!(c.epoch, 1);
        assert_eq!(c.mint_epochs, 1);
        // 1% of supply minted, all of it to the only locker, paid out unlocked.
        assert_eq!(c.total_supply, GENESIS + GENESIS / 100);
        assert_eq!(c.locked_of(alice()).0, GENESIS * 7 / 10, "principal is untouched by the mint");
        assert_eq!(c.total_locked, GENESIS * 7 / 10, "locked total equals the sum of positions, exactly");
        let paid = c.ft_balance_of(alice()).0;
        assert!(paid.abs_diff(GENESIS / 100) < DUST, "the mint is spendable and paid out unlocked (got {paid})");
        assert_eq!(c.history.len(), 1);
        assert!(c.history[0].action.starts_with("mint"));
    }

    #[test]
    fn the_mint_stops_at_the_supply_ceiling() {
        // Without this, 1% of the *current* supply every epoch compounds: at a 60 second epoch it passes
        // u128 in about two days, and with overflow checks on, tick would panic and never run again.
        let mut c = deploy();
        let mut ts = 0;

        // A lock lasts at most 30 epochs, so this is what a keeper does: renew, tick, renew. That also
        // means the ceiling has to be reachable in real use, not only in theory.
        for _ in 0..7 {
            ctx(alice(), ts);
            let free = c.ft_balance_of(alice()).0;
            if free > 0 {
                c.lock(U128(free), 30);
            }
            for _ in 0..30 {
                ts += EPOCH;
                ctx(alice(), ts);
                c.tick();
            }
        }

        assert_eq!(c.max_supply, GENESIS * 4);
        assert_eq!(c.total_supply, c.max_supply, "supply stops at 4x genesis");
        // the last row may be an expired-lock epoch, so look for the ceiling anywhere in the window
        assert!(
            c.history.iter().any(|h| h.action == "capped"),
            "the ceiling is visible in the history: {:?}",
            c.history.iter().map(|h| &h.action).collect::<Vec<_>>()
        );

        // still ticking, still recording: a cap is not a stop.
        ts += EPOCH;
        ctx(alice(), ts);
        c.tick();
        assert_eq!(c.total_supply, c.max_supply);
        assert!(c.epoch > 200);
    }

    #[test]
    fn nobody_locking_burns_the_reserve() {
        let mut c = deploy();
        let before = c.total_supply;
        let reserve_before = c.reserve;
        ctx(bob(), EPOCH);
        c.tick();
        assert_eq!(c.burn_epochs, 1);
        assert_eq!(c.total_supply, before - before / 50); // 2% burned
        assert_eq!(c.reserve, reserve_before - before / 50);
        assert!(c.history[0].action.starts_with("burn"));
    }

    #[test]
    fn burn_can_never_take_more_than_the_reserve() {
        let mut c = deploy();
        // Roll many epochs with no lockers until the reserve is gone.
        for e in 1..=40u64 {
            ctx(bob(), EPOCH * e);
            c.tick();
        }
        assert!(c.reserve < GENESIS * 3 / 10);
        let mut e = 41u64;
        while c.reserve > 0 && e < 400 {
            ctx(bob(), EPOCH * e);
            c.tick();
            e += 1;
        }
        assert_eq!(c.reserve, 0, "reserve should be fully spent by the burn rule");
        let supply_floor = c.total_supply;
        ctx(bob(), EPOCH * (e + 1));
        c.tick();
        assert_eq!(c.total_supply, supply_floor, "no burn is possible once the reserve is empty");
    }

    #[test]
    fn early_exit_burns_a_tenth_and_pays_the_rest() {
        let mut c = deploy();
        ctx(alice(), 0);
        let free_before = c.balance_of(&alice());
        c.lock(U128(free_before), 10);

        ctx(alice(), EPOCH);
        c.tick();
        let locked = c.locked_of(alice()).0;
        let supply_before = c.total_supply;
        c.unlock();

        let penalty = locked * 1_000 / 10_000;
        let reward = GENESIS / 100; // the only locker earned the whole mint when it settled
        assert_eq!(c.total_supply, supply_before - penalty);
        assert_eq!(c.total_locked, 0, "the lock is gone, and nothing was left behind");
        let diff = c.balance_of(&alice()).abs_diff(locked - penalty + reward);
        assert!(diff < DUST, "principal back, minus the burn, plus the reward (off by {diff})");
    }

    #[test]
    fn exiting_after_the_deadline_is_free() {
        let mut c = deploy();
        ctx(alice(), 0);
        c.lock(U128(GENESIS * 7 / 10), 2);

        ctx(alice(), EPOCH);
        c.tick();
        ctx(alice(), EPOCH * 2);
        c.tick();
        assert_eq!(c.epoch, 2);

        let supply_before = c.total_supply;
        ctx(alice(), EPOCH * 2);
        c.unlock();
        assert_eq!(c.total_supply, supply_before, "no penalty after the deadline");
        assert!(c.balance_of(&alice()) > 0);
    }

    #[test]
    #[should_panic(expected = "epoch not finished yet")]
    fn tick_before_the_epoch_ends_is_rejected() {
        let mut c = deploy();
        ctx(bob(), EPOCH - 1);
        c.tick();
    }

    #[test]
    fn transfer_cannot_touch_locked_tokens() {
        let mut c = deploy();
        ctx(alice(), 0);
        c.ft_transfer(bob(), U128(GENESIS * 6 / 10));
        c.lock(U128(GENESIS / 10), 2);
        assert_eq!(c.balance_of(&bob()), GENESIS * 6 / 10);
        assert_eq!(c.locked_of(alice()).0, GENESIS / 10);
        // alice has nothing unlocked left, so any transfer must fail
        let err = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            ctx(alice(), 0);
            c.ft_transfer(bob(), U128(1));
        }));
        assert!(err.is_err());
    }

    #[test]
    fn a_lock_expires_on_its_own_and_grip_falls_with_it() {
        let mut c = deploy();
        ctx(alice(), 0);
        c.lock(U128(GENESIS * 7 / 10), 2); // whole live float, two epochs
        assert_eq!(c.locked_share_bps(), 10_000);

        ctx(bob(), EPOCH);
        c.tick();
        assert_eq!(c.mint_epochs, 1, "epoch 1 should mint");
        assert_eq!(c.total_locked, GENESIS * 7 / 10, "the mint is paid out unlocked");

        // epoch 2 is the deadline: the lock releases itself before the rule is evaluated
        ctx(bob(), EPOCH * 2);
        c.tick();
        assert_eq!(c.expired_locks, 1, "the lock should expire without anyone unlocking");
        assert_eq!(c.total_locked, 0, "the principal left the lock cleanly");
        assert_eq!(c.locked_share_bps(), 0);
        assert_eq!(c.burn_epochs, 1, "grip collapsed, so the burn fires");
        assert!(c.balance_of(&alice()) > 0, "tokens went back to the holder unlocked");
    }

    #[test]
    fn unlocking_after_your_lock_expired_is_a_no_op() {
        let mut c = deploy();
        ctx(alice(), 0);
        c.lock(U128(GENESIS / 10), 1);

        ctx(bob(), EPOCH);
        c.tick();
        assert_eq!(c.expired_locks, 1);

        let supply_before = c.total_supply;
        let free_before = c.balance_of(&alice());
        ctx(alice(), EPOCH);
        c.unlock(); // must not panic and must not burn anything
        assert_eq!(c.total_supply, supply_before);
        assert_eq!(c.balance_of(&alice()), free_before);
    }

    #[test]
    fn share_is_measured_against_live_float_not_raw_supply() {
        let c = deploy();
        assert_eq!(c.engaged(), GENESIS - c.reserve);
        // 0 locked against 7M float is 0 bps, against 10M raw supply it would still be 0,
        // so check the invariant with a real lock instead.
        let mut c = deploy();
        ctx(alice(), 0);
        c.lock(U128(GENESIS * 7 / 20), 5); // half the live float
        assert_eq!(c.locked_share_bps(), 5_000);
    }
}

"""Genuine signed ten-role, producer-backed valuation test universe."""

from ashare_pipeline.formal_valuation_adapter_contract import load_formal_valuation_adapter_registry
from ashare_pipeline.formal_valuation_engine import FormalValuationRepository
from tests.formal_policy_fixtures import add_valuation_adapter_document
from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture


class ValuationRuntimeFixture(PolicyRuntimeFixture):
    def __init__(self, *, peer_count=20, extra_members=()):
        if type(peer_count) is not int or peer_count < 3:
            raise ValueError("valuation fixture requires all three exchanges")
        securities = {"BJ430001": "general_nonfinancial"}
        securities.update({f"SH{600000 + index}": "general_nonfinancial"
                           for index in range(peer_count - 2)})
        securities["SZ000001"] = "general_nonfinancial"

        def choose_earnings_adapter(documents):
            rule = documents["cyclic"]["rules"]["general_nonfinancial_cyclic_top"]
            for dependency in rule["parameters"]["valuation_dependencies"]:
                if dependency["metric_id"] == "V.normalized_earnings_yield":
                    dependency.update(policy_dependency="affected", profit_semantic_id="cyclic_top",
                        adapter_id="fixture_profit_adapter", adapter_version="fixture-v1")
                else:
                    dependency.update(policy_dependency="unaffected", profit_semantic_id=None,
                        adapter_id=None, adapter_version=None)
            add_valuation_adapter_document(documents)
            # Keep market requests small while the genuine range producer
            # materializes every requested slice. The resulting full window
            # clears the independent no-effective-trade rule.
            for config in documents["source"]["range_configs"]:
                config["max_calendar_days_per_request"] = 1

        super().__init__(range_enabled=True, templates=securities, extra_members=extra_members, cyclic=True,
            noncyclic_ids=tuple(sorted(set(securities) - {"BJ430001"})),
            valuation_adapter=True, mutate=choose_earnings_adapter)
        self.templates = securities
        self.valuation_registry = load_formal_valuation_adapter_registry(self.bundle,
            scoring_registry=self.scoring, policy_registry=self.policy_registry)
        self.repository = FormalValuationRepository(self.feature_repository, self.context,
            self.range_store, registry_signature_verifier=self.verifier)
        self.valuation_feature_bundles = {}

    def populate_valuation_inputs(self):
        self.populate_policy_evidence(skip_financial=tuple(sorted(set(self.templates) - {"BJ430001"})),
            financial_overrides={"BJ430001": dict(current_profit=10.0,
                annual_profit=(4.0, 5.0, 6.0, 7.0, 8.0))})
        if callable(getattr(self, "_valuation_progress", None)):
            self._valuation_progress("policy_done", None)
        for index, sid in enumerate(sorted(self.templates)):
            self.put_financial(sid, {
                "V.enterprise_value_or_sustainable_roe": 0.1 + index / 1000,
                "V.normalized_earnings_yield": 0.20 if sid == "BJ430001" else 0.1 + index / 1000,
                "V.normalized_free_cash_flow_yield": 0.08 + index / 1000,
            })
            self.valuation_feature_bundles[sid] = self.persist_features(sid)
            if callable(getattr(self, "_valuation_progress", None)):
                self._valuation_progress("metric", sid)
        if callable(getattr(self, "_valuation_progress", None)):
            self._valuation_progress("metric_done", None)

    def build_adjusted_batch(self):
        return self.repository.build_batch(self.frozen.frozen_input_hash,
            scoring_registry=self.scoring, policy_registry=self.policy_registry,
            valuation_adapter_registry=self.valuation_registry)

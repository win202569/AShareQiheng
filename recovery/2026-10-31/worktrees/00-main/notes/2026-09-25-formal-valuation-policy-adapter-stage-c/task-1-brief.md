### Task 1: Versioned ten-role registry root

**Files:**
- Modify: `ashare_pipeline/formal_registry_manifest.py:24-35,154-210,218-260,377-488,560-727`
- Modify: `tests/test_formal_registry_manifest.py`
- Modify: `tests/test_formal_scoring_registry.py:46-86`

**Interfaces:**
- Consumes: 现有规范 JSON、根签名、child 签名和外层 root/child/role binding。
- Produces: `formal-registry-manifest-v2`；`FormalRegistryManifest.schema_version: str`；`FormalRegistryManifest.valuation_adapter_registry_hash: str | None`；`VerifiedRegistryBundle.roles: tuple[str, ...]`；v1 精确九角色、v2 精确十角色。

- [ ] **Step 1: 写 v1/v2 失败测试。**

```python
def test_v1_bundle_remains_valid_but_has_no_valuation_adapter_role(self):
    repository, manifest, _ = fixture_repository(schema_version="formal-registry-manifest-v1")
    bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)
    self.assertEqual(len(bundle.roles), 9)
    self.assertIsNone(bundle.manifest.valuation_adapter_registry_hash)
    with self.assertRaisesRegex(ValueError, "role is unavailable for this manifest version"):
        bundle.blob("valuation_adapter")

def test_v2_requires_exact_ten_roles_and_signed_adapter_binding(self):
    repository, manifest, _ = fixture_repository(schema_version="formal-registry-manifest-v2")
    bundle = FormalRegistryBundleLoader(repository, AcceptingVerifier()).load(manifest.manifest_hash)
    self.assertEqual(bundle.roles[-1], "valuation_adapter")
    self.assertEqual(bundle.blob("valuation_adapter").registry_hash,
                     manifest.valuation_adapter_registry_hash)
```

同时加入：v2 缺 child、重复 child hash、adapter child 自报错 role、错 root binding、错 approval ID、v1 偷带第十字段、未知 v3 schema、`object.__setattr__` 修改 schema/adapter hash 后 seal 失效。

- [ ] **Step 2: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest -v`

Expected: 新 v2 测试因 schema 和字段不存在而失败；既有 v1 测试仍通过到原断言位置。

- [ ] **Step 3: 实现版本化角色集合。**

```python
_ROLE_FIELDS_V1 = {
    "source": "source_registry_hash", "mapping": "mapping_registry_hash",
    "feature": "feature_registry_hash", "scoring": "scoring_registry_hash",
    "industry": "industry_registry_hash", "cyclic": "cyclic_registry_hash",
    "redline": "redline_registry_hash", "status": "status_registry_hash",
    "event": "event_registry_hash",
}
_ROLE_FIELDS_V2 = dict(_ROLE_FIELDS_V1,
    valuation_adapter="valuation_adapter_registry_hash")
_ROLE_FIELDS_BY_SCHEMA = {
    "formal-registry-manifest-v1": _ROLE_FIELDS_V1,
    "formal-registry-manifest-v2": _ROLE_FIELDS_V2,
}

def role_fields_for_schema(schema_version):
    fields = _ROLE_FIELDS_BY_SCHEMA.get(schema_version)
    if fields is None:
        raise ValueError("registry manifest schema_version is invalid")
    return fields
```

把 schema_version 和可空 adapter hash 纳入 manifest snapshot/fingerprint；`from_signed_bytes` 先读 schema 再计算精确 keys；v1 构造时 adapter hash 固定为 `None`，v2 必须是唯一 SHA-256。bundle 的 `roles` 从 manifest schema 导出，`require_official`、`blob`、`load` 和 `assert_member_hashes` 只接受该 schema 的精确角色集合。

- [ ] **Step 4: 更新签名图夹具，保持默认 v1。**

```python
def signed_graph(*, mutate=None, context=False,
                 manifest_version="formal-registry-manifest-v1"):
    verifier = HmacVerifier()
    wrapper = fixture_wire()
    scoring = wrapper["scoring"]
    slots = scoring.pop("fixture_feature_slots")
    policies = scoring.pop("fixture_policies")
    scoring["purpose"] = "official"
    configs = []
    if context:
        from tests.test_formal_context_repository import descriptor
        from tests.test_formal_sources import config
        wrapper["descriptors"] = [descriptor()]
        configs = [config(dataset="fixture-state", exchange_scope="SZ")]
    documents = {role: dict(registry_role=role, schema_version="fixture-v1")
                 for role in ROLES}
    documents["source"] = dict(registry_role="source",
        schema_version="formal-source-registry-v1", configs=configs)
    documents["feature"] = dict(registry_role="feature",
        schema_version="formal-feature-registry-v1",
        contract_version="formal-features-v1",
        source_registry_hash=hashlib.sha256(
            canonical(documents["source"])).hexdigest(),
        mapping_registry_hash=hashlib.sha256(
            canonical(documents["mapping"])).hexdigest(),
        template_ids=sorted(TEMPLATES),
        slots=sorted(slots, key=lambda item: item["slot_id"]))
    for role, policy in policies.items():
        policy["purpose"] = "official"
        documents[role] = policy
        scoring["policy_contracts"][role]["registry_hash"] = hashlib.sha256(
            canonical(policy)).hexdigest()
    documents["scoring"] = wrapper
    if mutate:
        mutate(documents)
    active_roles = tuple(ROLES)
    if manifest_version == "formal-registry-manifest-v2":
        active_roles += ("valuation_adapter",)
    if set(documents) != set(active_roles):
        raise ValueError("fixture documents differ from manifest roles")
    raws = {role: canonical(documents[role]) for role in active_roles}
    hashes = {role + "_registry_hash": hashlib.sha256(raw).hexdigest()
              for role, raw in raws.items()}
    root = canonical(dict(schema_version=manifest_version, purpose="official",
                          approval_id="test-graph-approval", **hashes))
    manifest = FormalRegistryManifest.from_signed_bytes(
        root, verifier.sign(root), "scoring-test-key", verifier)
    blobs = {}
    for role, raw in raws.items():
        digest = hashlib.sha256(raw).hexdigest()
        binding = canonical(dict(child_sha256=digest,
            registry_manifest_hash=manifest.manifest_hash,
            registry_role=role))
        blobs[digest] = VerifiedRegistryBlob(
            role, digest, raw, verifier.sign(raw), "scoring-test-key",
            manifest.approval_id, manifest.manifest_hash,
            verifier.sign(binding), "scoring-test-key")
    repository = InMemoryRepository(manifest, blobs)
    bundle = FormalRegistryBundleLoader(repository, verifier).load(
        manifest.manifest_hash)
    feature = bundle.blob("feature")
    vocabulary = load_signed_feature_registry(
        feature.canonical_json, feature.signature, feature.key_id, verifier,
        registry_manifest=bundle.manifest)
    return bundle, vocabulary, repository, verifier
```

默认参数必须让现有测试继续得到 v1；v2 的 mutate 必须显式加入 `documents["valuation_adapter"]`，否则精确集合检查失败。

- [ ] **Step 5: 运行 GREEN 和旧图回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_feature_contract tests.test_formal_sources -v`

Expected: 全部 PASS；v1 和 v2 的角色数、签名、seal 与篡改路径均有明确断言。

- [ ] **Step 6: 提交 C1。**

```powershell
git add ashare_pipeline/formal_registry_manifest.py tests/test_formal_registry_manifest.py tests/test_formal_scoring_registry.py
git commit -m "feat: version the formal registry root for valuation adapters"
```


# Backend module & function reference

This is generated from the source: every public service function, route handler
and WebSocket handler, with its signature and purpose. Keep docstrings in sync.

## `app.services.admin`

Super admin bootstrap and gym-admin management.


| Function | Purpose |
|---|---|
| `create_gym_admin(session: 'Session', email: 'str', password: 'str', display_name: 'str', document_id: 'str | None' = None) -> 'User'` | — |
| `delete_user(session: 'Session', user: 'User') -> 'None'` | Hard delete a user and all their data (ordered to satisfy FK constraints). |
| `ensure_superadmin(session: 'Session') -> 'User | None'` | Create/ensure the super admin from environment variables (idempotent). |
| `get_user(session: 'Session', user_id: 'str') -> 'User | None'` | — |
| `list_gym_admins(session: 'Session') -> 'list[User]'` | — |
| `list_users(session: 'Session', role: 'str | None' = None, search: 'str | None' = None) -> 'list[User]'` | — |
| `reset_password(session: 'Session', user: 'User', password: 'str') -> 'User'` | — |
| `serialize_user(user: 'User') -> 'dict'` | — |
| `set_active(session: 'Session', user: 'User', active: 'bool') -> 'User'` | — |
| `set_role(session: 'Session', user: 'User', role: 'str') -> 'User'` | — |
| `update_user(session: 'Session', user: 'User', data: 'dict') -> 'User'` | — |

## `app.services.auth`

Authentication: password hashing, JWT tokens and the current-user dependency.


| Function | Purpose |
|---|---|
| `create_access_token(user_id: 'str') -> 'str'` | — |
| `current_user(credentials: 'HTTPAuthorizationCredentials | None' = Depends(dependency=<fastapi.security.http.HTTPBearer object at 0x7f622f950d70>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'User'` | — |
| `decode_token(token: 'str') -> 'dict'` | — |
| `hash_password(password: 'str') -> 'str'` | — |
| `require_gym_admin(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None)) -> 'User'` | — |
| `require_super_admin(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None)) -> 'User'` | — |
| `verify_password(password: 'str', stored: 'str') -> 'bool'` | — |

## `app.services.calendar`

Cycle/gestation calendar service.


| Function | Purpose |
|---|---|
| `build_calendar(profile: 'Profile | None', month: 'str | None' = None, language: 'str' = 'EN') -> 'CycleCalendar'` | — |

## `app.services.capture`

Capture flow: simulated telemetry -> core -> routine -> persistence.


| Function | Purpose |
|---|---|
| `capture(session: 'Session', user: 'User', profile: 'Profile | None', language: 'str' = 'EN', scenario: 'str | None' = None, muscle_groups: 'list[str] | None' = None, exercises_count: 'int | None' = None, time_budget_minutes: 'int | None' = None, energy_level: 'str | None' = None, include_warmup: 'bool' = True) -> 'dict'` | Run the simulated capture and persist session, telemetry and routine. |

## `app.services.catalog`

Exercise catalog service.


| Function | Purpose |
|---|---|
| `get_catalog(language: 'str' = 'EN') -> 'list[dict[str, Any]]'` | Return the catalog with text localized to `language`. |
| `list_muscle_groups() -> 'list[str]'` | — |

## `app.services.cycles`

Cycle and gestation timeline computation.


| Function | Purpose |
|---|---|
| `compute_timeline(profile: 'Profile', today: 'date | None' = None) -> 'dict | None'` | Compute the current cycle day/phase or gestational week/trimester. |

## `app.services.engine`

Deterministic core orchestration.


| Function | Purpose |
|---|---|
| `engine_result(frame: 'dict[str, Any]') -> 'EngineResult'` | Validate a telemetry frame and return the deterministic `EngineResult`. |
| `evaluate_frame(frame: 'dict[str, Any]') -> 'dict[str, Any]'` | Validate a telemetry frame and return the deterministic decision. |

## `app.services.gyms`

Gyms, machines and memberships (admin + athlete side).


| Function | Purpose |
|---|---|
| `add_machine(session: 'Session', gym: 'Gym', name: 'dict', purpose: 'dict | None' = None, image_url: 'str | None' = None, weight_factor: 'float' = 1.0, exercise_ids: 'list[str] | None' = None, equipment_key: 'str | None' = None, equipment_type: 'str | None' = None) -> 'GymMachine'` | — |
| `available_equipment_keys(session: 'Session', profile: 'Profile') -> 'set[str] | None'` | Equipment keys available from the gym inventory (None = unknown, don't filter). |
| `available_exercise_ids(session: 'Session', profile: 'Profile') -> 'set[str]'` | Exercise ids explicitly covered by the gym inventory (bypass equipment filter). |
| `build_i18n(text: 'str', ai_value: 'object' = None) -> 'dict'` | Build a localized dict from text, using AI translations when valid. |
| `create_gym(session: 'Session', user: 'User', name: 'str') -> 'Gym'` | — |
| `delete_gym(session: 'Session', gym: 'Gym') -> 'None'` | Delete a gym: its memberships, dangling active pointers and machines. |
| `delete_machine(session: 'Session', machine: 'GymMachine') -> 'None'` | — |
| `get_by_code(session: 'Session', code: 'str') -> 'Gym | None'` | — |
| `get_by_id(session: 'Session', gym_id: 'str') -> 'Gym | None'` | — |
| `get_machine(session: 'Session', gym: 'Gym', machine_id: 'str') -> 'GymMachine | None'` | — |
| `gym_inventory(session: 'Session', profile: 'Profile') -> 'list[GymMachine]'` | — |
| `join_gym(session: 'Session', profile: 'Profile', gym: 'Gym') -> 'GymMembership'` | Join a gym idempotently and make it active if nothing else is. |
| `joined_gyms(session: 'Session', profile: 'Profile', language: 'str' = 'EN') -> 'list[dict]'` | Resolve all joined gyms in O(G + M) instead of N+1 queries. |
| `leave_gym(session: 'Session', profile: 'Profile', gym_id: 'str') -> 'bool'` | — |
| `list_memberships(session: 'Session', profile: 'Profile') -> 'list[GymMembership]'` | — |
| `list_owned(session: 'Session', user: 'User') -> 'list[Gym]'` | — |
| `localize(value: 'object', language: 'str' = 'EN') -> 'str'` | Resolve a localized value (dict or plain string) to a single string. |
| `rename_gym(session: 'Session', gym: 'Gym', name: 'str') -> 'Gym'` | — |
| `resolved_exercise_ids(machine: 'GymMachine') -> 'list[str]'` | Exercise ids a machine covers: declared ids, plus a fuzzy name fallback. |
| `sanitize_exercise_ids(ids: 'list[str] | None') -> 'list[str]'` | Keep only catalog exercise ids (drops AI hallucinations) and deduplicate. |
| `serialize_gym(gym: 'Gym', language: 'str' = 'EN') -> 'dict'` | — |
| `serialize_joined_gym(gym: 'Gym', active: 'bool', joined_at=None, machines=None, language: 'str' = 'EN') -> 'dict'` | — |
| `serialize_machine(machine: 'GymMachine', language: 'str' = 'EN') -> 'dict'` | Serialize a gym machine with localized name/purpose. |
| `set_active_gym(session: 'Session', profile: 'Profile', gym_id: 'str') -> 'bool'` | — |
| `station_index(session: 'Session', profile: 'Profile', language: 'str' = 'EN') -> 'tuple[dict[str, dict], set[str]]'` | Index the active gym's machines by exercise id. |
| `update_machine(session: 'Session', machine: 'GymMachine', *, name: 'dict | None' = None, purpose: 'dict | None' = None, image_url: 'str | None' = None, weight_factor: 'float | None' = None, exercise_ids: 'list[str] | None' = None, equipment_key: 'str | None' = None, equipment_type: 'str | None' = None) -> 'GymMachine'` | — |

## `app.services.loads`

Baseline-load adjustment.


| Function | Purpose |
|---|---|
| `adjust_entries(entries: 'list[dict[str, Any]]', loads: 'Iterable[ExerciseLoad]', k_load: 'float | None', energy_level: 'object | None' = None, machine_factors: 'dict[str, float] | None' = None) -> 'list[dict[str, Any]]'` | — |
| `load_multiplier(k_load: 'float | None', energy_level: 'object | None' = None) -> 'float'` | — |
| `variation_pct(k_load: 'float | None', energy_level: 'object | None' = None) -> 'float'` | — |

## `app.services.machines`

Gym machine catalog service.


| Function | Purpose |
|---|---|
| `factor_for_exercise(exercise_id: 'str', available_machine_ids: 'list[str] | None' = None) -> 'float'` | Weight factor of the first available machine supporting the exercise. |
| `list_machines(language: 'str' = 'EN') -> 'list[dict[str, Any]]'` | — |
| `machine_weight_factor(machine_id: 'str | None') -> 'float'` | — |

## `app.services.ordering`

Routine ordering.


| Function | Purpose |
|---|---|
| `order_entries(entries: 'list[dict[str, Any]]', phase: 'str | None' = None, language: 'str' = 'EN') -> 'list[dict[str, Any]]'` | — |

## `app.services.profiles`

In-memory user profiles and energy check-ins.


| Function | Purpose |
|---|---|
| `add_energy_checkin(checkin: 'EnergyCheckIn') -> 'EnergyCheckIn'` | — |
| `clear() -> 'None'` | — |
| `get_profile(profile_id: 'str') -> 'UserProfile | None'` | — |
| `list_energy(profile_id: 'str | None' = None) -> 'list[EnergyCheckIn]'` | — |
| `list_profiles() -> 'list[UserProfile]'` | — |
| `upsert_profile(profile: 'UserProfile') -> 'UserProfile'` | — |

## `app.services.profiles_db`

Profile persistence for the onboarding and settings flow.


| Function | Purpose |
|---|---|
| `get_profile(session: 'Session', user: 'User') -> 'Profile | None'` | — |
| `upsert_profile(session: 'Session', user: 'User', data: 'dict[str, Any]') -> 'Profile'` | — |

## `app.services.routines`

Routine generation service.


| Function | Purpose |
|---|---|
| `core_result_for_request(request: 'RoutineRequest') -> 'EngineResult | None'` | — |
| `generate_routine(request: 'RoutineRequest', engine: 'str' = 'deterministic', profile_id: 'str | None' = None, preferred_exercise_ids: 'Iterable[str] | None' = None, contraindicated_patterns: 'Iterable[str] | None' = None, gym_machines: 'list[dict[str, Any]] | None' = None, assessment: 'dict[str, Any] | None' = None, equipment_keys: 'Iterable[str] | None' = None, available_exercise_ids: 'Iterable[str] | None' = None) -> 'dict[str, Any]'` | Generate a routine. |
| `max_impact_for(core_result: 'EngineResult | None') -> 'str'` | — |

## `app.services.sharing`

Sharing: create guest links and build the read-only shared profile.


| Function | Purpose |
|---|---|
| `build_shared_profile(session: 'Session', token: 'str', language: 'str' = 'EN') -> 'SharedProfile | None'` | — |
| `create_share(session: 'Session', user: 'User', role: 'str', permissions: 'list[str]', label: 'str | None' = None) -> 'ShareLink'` | — |
| `delete_share(session: 'Session', user: 'User', token: 'str') -> 'bool'` | — |
| `find_share(session: 'Session', token: 'str') -> 'ShareLink | None'` | — |
| `list_shares(session: 'Session', user: 'User') -> 'list[ShareLink]'` | — |
| `serialize_link(link: 'ShareLink') -> 'dict'` | — |

## `app.services.stats`

Training streak and weekly stats.


| Function | Purpose |
|---|---|
| `compute_stats(session: 'Session', user: 'User', profile: 'Profile | None', today: 'date | None' = None) -> 'dict'` | — |

## `app.services.supplements`

Supplement advice and daily macronutrient estimate.


| Function | Purpose |
|---|---|
| `catalog(language: 'str' = 'EN') -> 'list[dict]'` | Raw supplement catalog with brands/frequency for reminders. |
| `estimate_daily_macros(request: 'SupplementRequest') -> 'MacroNutrients | None'` | Estimate a daily calorie and macro target (Mifflin-St Jeor, female). |
| `recommend(request: 'SupplementRequest') -> 'SupplementAdvice'` | — |

## `app.services.symptoms`

Apply symptoms to a generated routine (block risky exercises, add advice).


| Function | Purpose |
|---|---|
| `apply_symptoms(entries: 'list[dict[str, Any]]', symptom_ids: 'list[str]', language: 'str' = 'EN') -> 'tuple[list[dict[str, Any]], list[str], bool]'` | AI-first: only absolute contraindications stop loading; else no blocking here. |
| `contraindicated_patterns(symptom_ids: 'list[str]') -> 'list[str]'` | Movement patterns to avoid given the declared symptoms. |

## `app.services.validation`

Name and identity validation shared by registration, gyms and users.


| Function | Purpose |
|---|---|
| `normalize_name(value: 'str') -> 'str'` | — |
| `validate_document_id(value: 'str') -> 'str'` | — |
| `validate_gym_name(value: 'str') -> 'str'` | — |
| `validate_name(value: 'str', *, field: 'str' = 'name', reserved: 'bool' = True) -> 'str'` | Return the normalized name or raise ``ValueError`` with a clear message. |
| `validate_person_name(value: 'str') -> 'str'` | — |

## `app.api.auth`

Authentication routes: register, login and current user.


| Function | Purpose |
|---|---|
| `login(payload: 'LoginIn', session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict'` | — |
| `me(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None)) -> 'dict'` | — |
| `register(payload: 'RegisterIn', session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict'` | — |

## `app.api.routes`

REST routes.


| Function | Purpose |
|---|---|
| `activate_gym(gym_id: 'str', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `add_energy(payload: 'dict[str, Any]') -> 'dict[str, Any]'` | — |
| `add_gym_machine(gym_id: 'str', payload: 'dict[str, Any]', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_activate_user(user_id: 'str', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_create_gym_admin(payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_deactivate_user(user_id: 'str', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_delete_user(user_id: 'str', payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'Response'` | — |
| `admin_get_user(user_id: 'str', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_list_gym_admins(user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `admin_list_gyms(language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `admin_list_users(role: 'str | None' = Query(None), search: 'str | None' = Query(None), user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `admin_me(user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_reset_password(user_id: 'str', payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_set_role(user_id: 'str', payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `admin_update_user(user_id: 'str', payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function require_super_admin at 0x7f622f9edd20>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `catalog(language: 'str' = Query(EN)) -> 'list[dict[str, Any]]'` | — |
| `create_gym(payload: 'dict[str, Any]', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function require_gym_admin at 0x7f622f9ede80>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `create_or_update_profile(payload: 'dict[str, Any]') -> 'dict[str, Any]'` | — |
| `create_routine(payload: 'dict[str, Any]', engine: 'str' = Query(simulator), profile_id: 'str | None' = Query(None)) -> 'dict[str, Any]'` | — |
| `delete_gym(gym_id: 'str', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'Response'` | — |
| `delete_gym_machine(gym_id: 'str', machine_id: 'str', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'Response'` | — |
| `exercise_alternatives(exercise_id: 'str', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `exercise_variants(exercise_id: 'str', language: 'str' = Query(EN)) -> 'list[dict[str, Any]]'` | — |
| `get_calendar(month: 'str | None' = Query(None), language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `get_cycle(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `get_energy(profile_id: 'str | None' = Query(None)) -> 'list[dict[str, Any]]'` | — |
| `get_gym(code: 'str', language: 'str' = Query(EN), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `get_my_profile(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `get_profile(profile_id: 'str') -> 'dict[str, Any]'` | — |
| `get_profiles() -> 'list[dict[str, Any]]'` | — |
| `get_shared_profile(token: 'str', language: 'str' = Query(EN), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `get_shares(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `get_supplement_intakes(date_str: 'str | None' = Query(None), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `gym_qr(gym_id: 'str', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'Response'` | — |
| `health() -> 'dict[str, str]'` | — |
| `ingest_telemetry(frame: 'dict[str, Any]') -> 'dict[str, Any]'` | — |
| `join_gym(payload: 'dict[str, Any]', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `joined_gyms(language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `latest_routine(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `leave_gym(gym_id: 'str', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'Response'` | — |
| `machines(language: 'str' = Query(EN)) -> 'list[dict[str, Any]]'` | — |
| `muscle_groups() -> 'list[str]'` | — |
| `my_gyms(language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'list[dict[str, Any]]'` | — |
| `post_share(payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `remove_share(token: 'str', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `set_supplement_intake(payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `stats(user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `supplements(modality: 'str' = Query(MENSTRUAL_CYCLE), language: 'str' = Query(EN), objective: 'str | None' = Query(None), goal_phase: 'str | None' = Query(None), week: 'int | None' = Query(None), weight_kg: 'float | None' = Query(None), height_cm: 'float | None' = Query(None), body_fat_pct: 'float | None' = Query(None), age: 'int | None' = Query(None), daily_calories: 'int | None' = Query(None)) -> 'dict[str, Any]'` | — |
| `supplements_catalog_endpoint(language: 'str' = Query(EN)) -> 'list[dict[str, Any]]'` | — |
| `symptoms(language: 'str' = Query(EN)) -> 'list[dict[str, Any]]'` | — |
| `take_data(language: 'str' = Query(EN), scenario: 'str | None' = Query(None), muscle_groups: 'str | None' = Query(None), exercises_count: 'int | None' = Query(None), time_budget_minutes: 'int | None' = Query(None), energy_level: 'str | None' = Query(None), include_warmup: 'bool' = Query(True), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `update_gym(gym_id: 'str', payload: 'dict[str, Any]', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `update_gym_machine(gym_id: 'str', machine_id: 'str', payload: 'dict[str, Any]', language: 'str' = Query(EN), user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |
| `update_my_profile(payload: 'dict[str, Any]', user: 'User' = Depends(dependency=<function current_user at 0x7f622f9edbc0>, use_cache=True, scope=None), session: 'Session' = Depends(dependency=<function get_session at 0x7f622f9ed640>, use_cache=True, scope=None)) -> 'dict[str, Any]'` | — |

## `app.ws.routes`

WebSocket routes for continuous telemetry ingestion.


| Function | Purpose |
|---|---|
| `telemetry_socket(websocket: 'WebSocket') -> 'None'` | Receive telemetry frames and reply with the deterministic decision. |

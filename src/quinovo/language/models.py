"""Quinovo ontology language: versioned schema loaded from YAML."""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quinovo.policy import DEFAULT_AUTO_APPLY_MIN_CONFIDENCE

PropertyType = Literal["string", "integer", "number", "boolean"]
Cardinality = Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
ActionParamKind = Literal["object", "string", "integer", "number", "boolean"]

ProposalKind = Literal[
    "type_definition",
    "classification",
    "inference_rule",
    "link_type",
    "action_type",
    "action_application",
    "pack",
]
PROPOSAL_KINDS: tuple[str, ...] = get_args(ProposalKind)


class QuinovoModel(BaseModel):
    """Shared base for every pack/config model: unknown keys are an error."""

    model_config = ConfigDict(extra="forbid")


class ObjectRef(QuinovoModel):
    """The one canonical object reference shape: {"type": "Package", "id": "box-1"}."""

    type: str
    id: str


class PropertyDef(QuinovoModel):
    api_name: str
    type: PropertyType
    required: bool = True
    description: str = ""


class SharedPropertyDef(PropertyDef):
    pass


class InterfaceDef(QuinovoModel):
    api_name: str
    description: str = ""
    properties: list[str] = Field(default_factory=list)


class ObjectTypeDef(QuinovoModel):
    api_name: str
    primary_key: str
    title_property: str
    description: str = ""
    implements: list[str] = Field(default_factory=list)
    properties: list[PropertyDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def primary_key_exists(self) -> ObjectTypeDef:
        names = {p.api_name for p in self.properties}
        if self.primary_key not in names:
            raise ValueError(
                f"{self.api_name}: primary_key {self.primary_key!r} is not a property"
            )
        if self.title_property not in names:
            raise ValueError(
                f"{self.api_name}: title_property {self.title_property!r} is not a property"
            )
        return self


class LinkTypeDef(QuinovoModel):
    api_name: str
    from_type: str
    to_type: str
    from_name: str
    to_name: str
    cardinality: Cardinality
    description: str = ""


class ActionParameterDef(QuinovoModel):
    api_name: str
    type: ActionParamKind = "object"
    object_type: str | None = None

    @model_validator(mode="after")
    def object_params_named(self) -> ActionParameterDef:
        if self.type == "object" and not self.object_type:
            raise ValueError(f"parameter {self.api_name}: object type requires object_type")
        return self


class ActionSetEdit(QuinovoModel):
    parameter: str
    set: dict[str, str] = Field(default_factory=dict)
    delete: bool = False


class ActionCreate(QuinovoModel):
    object_type: str
    id_parameter: str
    set: dict[str, str] = Field(default_factory=dict)


class ActionTypeDef(QuinovoModel):
    api_name: str
    description: str = ""
    parameters: list[ActionParameterDef]
    edits: list[ActionSetEdit] = Field(default_factory=list)
    creates: list[ActionCreate] = Field(default_factory=list)
    mcp_requires_recommendation: bool = False
    unattended: bool = False
    approval_required: bool = False


class OntologyMeta(QuinovoModel):
    api_name: str
    display_name: str
    description: str = ""
    auto_apply_min_confidence: float = DEFAULT_AUTO_APPLY_MIN_CONFIDENCE


class Ontology(QuinovoModel):
    ontology: OntologyMeta
    shared_properties: list[SharedPropertyDef] = Field(default_factory=list)
    interfaces: list[InterfaceDef] = Field(default_factory=list)
    object_types: list[ObjectTypeDef] = Field(default_factory=list)
    link_types: list[LinkTypeDef] = Field(default_factory=list)
    action_types: list[ActionTypeDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_and_resolved(self) -> Ontology:
        shared = {item.api_name: item for item in self.shared_properties}
        if len(shared) != len(self.shared_properties):
            raise ValueError("duplicate shared property api_name")

        interface_names = [item.api_name for item in self.interfaces]
        if len(interface_names) != len(set(interface_names)):
            raise ValueError("duplicate interface api_name")
        interfaces = {item.api_name: item for item in self.interfaces}
        for iface in self.interfaces:
            for prop in iface.properties:
                if prop not in shared:
                    raise ValueError(
                        f"interface {iface.api_name}: property {prop!r} is not a shared_property"
                    )

        for obj in self.object_types:
            seen = {p.api_name: p for p in obj.properties}
            for iface_name in obj.implements:
                iface = interfaces.get(iface_name)
                if iface is None:
                    raise ValueError(f"{obj.api_name}: unknown interface {iface_name!r}")
                for prop_name in iface.properties:
                    if prop_name in seen:
                        continue
                    shared_def = shared[prop_name]
                    obj.properties.append(
                        PropertyDef(
                            api_name=shared_def.api_name,
                            type=shared_def.type,
                            required=shared_def.required,
                            description=shared_def.description,
                        )
                    )
                    seen[prop_name] = obj.properties[-1]
            names = {p.api_name for p in obj.properties}
            if obj.primary_key not in names:
                raise ValueError(
                    f"{obj.api_name}: primary_key {obj.primary_key!r} is not a property"
                )
            if obj.title_property not in names:
                raise ValueError(
                    f"{obj.api_name}: title_property {obj.title_property!r} is not a property"
                )

        object_names = [o.api_name for o in self.object_types]
        if len(object_names) != len(set(object_names)):
            raise ValueError("duplicate object type api_name")
        object_set = set(object_names)

        link_names = [link.api_name for link in self.link_types]
        if len(link_names) != len(set(link_names)):
            raise ValueError("duplicate link type api_name")

        action_names = [a.api_name for a in self.action_types]
        if len(action_names) != len(set(action_names)):
            raise ValueError("duplicate action type api_name")

        for link in self.link_types:
            if link.from_type not in object_set:
                raise ValueError(
                    f"link {link.api_name}: from_type {link.from_type!r} is not an object type"
                )
            if link.to_type not in object_set:
                raise ValueError(
                    f"link {link.api_name}: to_type {link.to_type!r} is not an object type"
                )

        for action in self.action_types:
            params = {p.api_name: p for p in action.parameters}
            for param in action.parameters:
                if param.type == "object" and param.object_type not in object_set:
                    raise ValueError(
                        f"action {action.api_name}: parameter "
                        f"{param.api_name} object_type {param.object_type!r} unknown"
                    )
            for edit in action.edits:
                if edit.parameter not in params:
                    raise ValueError(
                        f"action {action.api_name}: edit parameter "
                        f"{edit.parameter!r} is not declared"
                    )
            for created in action.creates:
                if created.object_type not in object_set:
                    raise ValueError(
                        f"action {action.api_name}: create type {created.object_type!r} unknown"
                    )
                if created.id_parameter not in params:
                    raise ValueError(
                        f"action {action.api_name}: create id_parameter "
                        f"{created.id_parameter!r} is not declared"
                    )

        return self

    def object_type(self, api_name: str) -> ObjectTypeDef:
        for item in self.object_types:
            if item.api_name == api_name:
                return item
        raise KeyError(api_name)

    def link_type(self, api_name: str) -> LinkTypeDef:
        for item in self.link_types:
            if item.api_name == api_name:
                return item
        raise KeyError(api_name)

    def action_type(self, api_name: str) -> ActionTypeDef:
        for item in self.action_types:
            if item.api_name == api_name:
                return item
        raise KeyError(api_name)

    def interface(self, api_name: str) -> InterfaceDef:
        for item in self.interfaces:
            if item.api_name == api_name:
                return item
        raise KeyError(api_name)

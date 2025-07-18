from re import compile as re_compile
from typing import Any, Dict, List, Optional

from moto.core.base_backend import BackendDict, BaseBackend
from moto.core.common_models import BaseModel
from moto.core.utils import utcnow
from moto.utilities.paginator import paginate
from moto.utilities.utils import get_partition

from ..moto_api._internal import mock_random
from .exceptions import (
    CacheClusterAlreadyExists,
    CacheClusterNotFound,
    CacheSubnetGroupAlreadyExists,
    CacheSubnetGroupNotFound,
    InvalidARNFault,
    InvalidParameterCombinationException,
    InvalidParameterValueException,
    InvalidSubnet,
    UserAlreadyExists,
    UserNotFound,
)
from .utils import PAGINATION_MODEL, AuthenticationTypes


class User(BaseModel):
    def __init__(
        self,
        account_id: str,
        region: str,
        user_id: str,
        user_name: str,
        access_string: str,
        engine: str,
        no_password_required: bool,
        passwords: Optional[List[str]] = None,
        authentication_type: Optional[str] = None,
    ):
        self.id = user_id
        self.name = user_name
        self.engine = engine

        self.passwords = passwords or []
        self.access_string = access_string
        self.no_password_required = no_password_required
        self.status = "active"
        self.minimum_engine_version = "6.0"
        self.usergroupids: List[str] = []
        self.region = region
        self.arn = f"arn:{get_partition(self.region)}:elasticache:{self.region}:{account_id}:user:{self.id}"
        self.authentication_type = authentication_type


class CacheCluster(BaseModel):
    def __init__(
        self,
        account_id: str,
        region_name: str,
        cache_cluster_id: str,
        replication_group_id: Optional[str],
        az_mode: Optional[str],
        preferred_availability_zone: Optional[str],
        num_cache_nodes: Optional[int],
        cache_node_type: Optional[str],
        engine: Optional[str],
        engine_version: Optional[str],
        cache_parameter_group_name: Optional[str],
        cache_subnet_group_name: Optional[str],
        transit_encryption_enabled: Optional[bool],
        network_type: Optional[str],
        ip_discovery: Optional[str],
        snapshot_name: Optional[str],
        preferred_maintenance_window: Optional[str],
        port: Optional[int],
        notification_topic_arn: Optional[str],
        auto_minor_version_upgrade: Optional[bool],
        snapshot_retention_limit: Optional[int],
        snapshot_window: Optional[str],
        auth_token: Optional[str],
        outpost_mode: Optional[str],
        preferred_outpost_arn: Optional[str],
        preferred_availability_zones: Optional[List[str]],
        cache_security_group_names: Optional[List[str]],
        security_group_ids: Optional[List[str]],
        tags: Optional[List[Dict[str, str]]],
        snapshot_arns: Optional[List[str]],
        preferred_outpost_arns: Optional[List[str]],
        log_delivery_configurations: List[Dict[str, Any]],
        cache_node_ids_to_remove: Optional[List[str]],
        cache_node_ids_to_reboot: Optional[List[str]],
    ):
        if tags is None:
            tags = []
        self.cache_cluster_id = cache_cluster_id
        self.az_mode = az_mode
        self.preferred_availability_zone = preferred_availability_zone
        self.preferred_availability_zones = preferred_availability_zones or []
        self.engine = engine or "redis"
        self.engine_version = engine_version
        if engine == "redis":
            self.num_cache_nodes = 1
            self.replication_group_id = replication_group_id
            self.snapshot_arns = snapshot_arns or []
            self.snapshot_name = snapshot_name
            self.snapshot_window = snapshot_window
        if engine == "memcached":
            if num_cache_nodes is None:
                self.num_cache_nodes = 1
            elif 1 <= num_cache_nodes <= 40:
                self.num_cache_nodes = num_cache_nodes
        self.cache_node_type = cache_node_type
        self.cache_parameter_group_name = cache_parameter_group_name
        self.cache_subnet_group_name = cache_subnet_group_name
        self.cache_security_group_names = cache_security_group_names or []
        self.security_group_ids = security_group_ids or []
        self.tags = tags
        self.preferred_maintenance_window = preferred_maintenance_window
        self.port = port or 6379
        self.notification_topic_arn = notification_topic_arn
        self.auto_minor_version_upgrade = auto_minor_version_upgrade
        self.snapshot_retention_limit = snapshot_retention_limit or 0
        self.auth_token = auth_token
        self.outpost_mode = outpost_mode
        self.preferred_outpost_arn = preferred_outpost_arn
        self.preferred_outpost_arns = preferred_outpost_arns or []
        self.log_delivery_configurations = log_delivery_configurations or []
        self.transit_encryption_enabled = transit_encryption_enabled
        self.network_type = network_type
        self.ip_discovery = ip_discovery
        self.cache_node_ids_to_remove = cache_node_ids_to_remove
        self.cache_node_ids_to_reboot = cache_node_ids_to_reboot

        self.cache_cluster_create_time = utcnow()
        self.auth_token_last_modified_date = utcnow()
        self.cache_cluster_status = "available"
        self.arn = f"arn:{get_partition(region_name)}:elasticache:{region_name}:{account_id}:cluster:{cache_cluster_id}"
        self.cache_node_id = str(mock_random.uuid4())

    def get_tags(self) -> List[Dict[str, str]]:
        return self.tags


class CacheSubnetGroup(BaseModel):
    def __init__(
        self,
        account_id: str,
        region_name: str,
        cache_subnet_group_name: str,
        cache_subnet_group_description: str,
        subnet_ids: List[str],
        tags: Optional[List[Dict[str, str]]],
    ):
        if tags is None:
            tags = []
        self.cache_subnet_group_name = cache_subnet_group_name
        self.cache_subnet_group_description = cache_subnet_group_description
        self.subnet_ids = subnet_ids
        self.tags = tags

        # Only import ec2_backends if necessary
        from moto.ec2.models import ec2_backends

        ec2_backend = ec2_backends[account_id][region_name]
        self.supported_network_types = []
        self.subnets_responses = []
        vpc_exists = False
        try:
            # Get VPC details from provided subnet IDs
            subnets = ec2_backend.describe_subnets(subnet_ids=subnet_ids)
            vpc_exists = True
        except Exception as e:
            # Should raise InvalidSubnet if subnet_ids are invalid
            if "InvalidSubnet" in str(e):
                for subnet_id in subnet_ids:
                    subnet_response: Dict[str, Any] = {}
                    subnet_response["subnet_id"] = subnet_id
                    subnet_response["subnet_az"] = {"Name": "us-east-1a"}
                    subnet_response["subnet_supported_network_types"] = ["ipv4"]
                    self.subnets_responses.append(subnet_response)
                vpcs = ["vpc-0123456789abcdef0"]
                self.supported_network_types = ["ipv4"]

        if vpc_exists:
            vpcs = []
            for subnet in subnets:
                subnet_response = {}
                vpcs.append(subnet.vpc_id)
                subnet_response["subnet_id"] = subnet.id
                subnet_response["subnet_az"] = subnet.availability_zone
                subnet_response["subnet_supported_network_types"] = []
                if subnet.vpc_id != vpcs[0]:
                    raise InvalidSubnet(subnet_id=subnet.id)

                # ipv6 native subnets only appends ipv6
                # You can't mix ipv6 native subnets with other types of subnets
                if subnet.ipv6_native:
                    self.supported_network_types.append("ipv6")
                    subnet_response["subnet_supported_network_types"].append("ipv6")

                # ipv4 only and dual_stack subnets both append ipv4
                elif subnet.cidr_block:
                    self.supported_network_types.append("ipv4")
                    subnet_response["subnet_supported_network_types"].append("ipv4")

                if subnet.ipv6_cidr_block_associations and subnet.cidr_block:
                    self.supported_network_types.append("dual_stack")
                    subnet_response["subnet_supported_network_types"].append(
                        "dual_stack"
                    )

                self.subnets_responses.append(subnet_response)

            if self.supported_network_types:
                self.supported_network_types = list(set(self.supported_network_types))

        self.arn = f"arn:{get_partition(region_name)}:elasticache:{region_name}:{account_id}:subnetgroup:{cache_subnet_group_name}"
        self.vpc_id = vpcs[0] if vpcs else None

    def get_tags(self) -> List[Dict[str, str]]:
        return self.tags


class ElastiCacheBackend(BaseBackend):
    """Implementation of ElastiCache APIs."""

    def __init__(self, region_name: str, account_id: str):
        super().__init__(region_name, account_id)
        self.arn_regex = re_compile(
            r"^arn:aws:elasticache:.*:[0-9]*:(cluster|snapshot|subnetgroup):.*$"
        )
        self.users = dict()
        self.users["default"] = User(
            account_id=self.account_id,
            region=self.region_name,
            user_id="default",
            user_name="default",
            engine="redis",
            access_string="on ~* +@all",
            no_password_required=True,
        )

        self.cache_clusters: Dict[str, Any] = dict()
        self.cache_subnet_groups: Dict[str, CacheSubnetGroup] = dict()

    def create_user(
        self,
        user_id: str,
        user_name: str,
        engine: str,
        passwords: List[str],
        access_string: str,
        no_password_required: bool,
        authentication_type: str,  # contain it to the str in the enums TODO
    ) -> User:
        if user_id in self.users:
            raise UserAlreadyExists

        if authentication_type not in AuthenticationTypes._value2member_map_:
            raise InvalidParameterValueException(
                f"Input Authentication type: {authentication_type} is not in the allowed list: [password,no-password-required,iam]"
            )

        if (
            no_password_required
            and authentication_type != AuthenticationTypes.NOPASSWORD
        ):
            raise InvalidParameterCombinationException(
                f"No password required flag is true but provided authentication type is {authentication_type}"
            )

        if passwords and authentication_type != AuthenticationTypes.PASSWORD:
            raise InvalidParameterCombinationException(
                f"Password field is not allowed with authentication type: {authentication_type}"
            )

        if not passwords and authentication_type == AuthenticationTypes.PASSWORD:
            raise InvalidParameterCombinationException(
                "A user with Authentication Mode: password, must have at least one password"
            )

        user = User(
            account_id=self.account_id,
            region=self.region_name,
            user_id=user_id,
            user_name=user_name,
            engine=engine,
            passwords=passwords,
            access_string=access_string,
            no_password_required=no_password_required,
            authentication_type=authentication_type,
        )
        self.users[user_id] = user
        return user

    def delete_user(self, user_id: str) -> User:
        if user_id in self.users:
            user = self.users[user_id]
            if user.status == "active":
                user.status = "deleting"
            return user
        raise UserNotFound(user_id)

    def describe_users(self, user_id: Optional[str]) -> List[User]:
        """
        Only the `user_id` parameter is currently supported.
        Pagination is not yet implemented.
        """
        if user_id:
            if user_id in self.users:
                user = self.users[user_id]
                if user.status == "deleting":
                    self.users.pop(user_id)
                return [user]
            else:
                raise UserNotFound(user_id)
        return list(self.users.values())

    def create_cache_cluster(
        self,
        cache_cluster_id: str,
        replication_group_id: str,
        az_mode: str,
        preferred_availability_zone: str,
        num_cache_nodes: int,
        cache_node_type: str,
        engine: str,
        engine_version: str,
        cache_parameter_group_name: str,
        cache_subnet_group_name: str,
        transit_encryption_enabled: bool,
        network_type: str,
        ip_discovery: str,
        snapshot_name: str,
        preferred_maintenance_window: str,
        port: int,
        notification_topic_arn: str,
        auto_minor_version_upgrade: bool,
        snapshot_retention_limit: int,
        snapshot_window: str,
        auth_token: str,
        outpost_mode: str,
        preferred_outpost_arn: str,
        preferred_availability_zones: List[str],
        cache_security_group_names: List[str],
        security_group_ids: List[str],
        tags: List[Dict[str, str]],
        snapshot_arns: List[str],
        preferred_outpost_arns: List[str],
        log_delivery_configurations: List[Dict[str, Any]],
        cache_node_ids_to_remove: List[str],
        cache_node_ids_to_reboot: List[str],
    ) -> CacheCluster:
        if cache_cluster_id in self.cache_clusters:
            raise CacheClusterAlreadyExists(cache_cluster_id)
        cache_cluster = CacheCluster(
            account_id=self.account_id,
            region_name=self.region_name,
            cache_cluster_id=cache_cluster_id,
            replication_group_id=replication_group_id,
            az_mode=az_mode,
            preferred_availability_zone=preferred_availability_zone,
            preferred_availability_zones=preferred_availability_zones,
            num_cache_nodes=num_cache_nodes,
            cache_node_type=cache_node_type,
            engine=engine,
            engine_version=engine_version,
            cache_parameter_group_name=cache_parameter_group_name,
            cache_subnet_group_name=cache_subnet_group_name,
            cache_security_group_names=cache_security_group_names,
            security_group_ids=security_group_ids,
            tags=tags,
            snapshot_arns=snapshot_arns,
            snapshot_name=snapshot_name,
            preferred_maintenance_window=preferred_maintenance_window,
            port=port,
            notification_topic_arn=notification_topic_arn,
            auto_minor_version_upgrade=auto_minor_version_upgrade,
            snapshot_retention_limit=snapshot_retention_limit,
            snapshot_window=snapshot_window,
            auth_token=auth_token,
            outpost_mode=outpost_mode,
            preferred_outpost_arn=preferred_outpost_arn,
            preferred_outpost_arns=preferred_outpost_arns,
            log_delivery_configurations=log_delivery_configurations,
            transit_encryption_enabled=transit_encryption_enabled,
            network_type=network_type,
            ip_discovery=ip_discovery,
            cache_node_ids_to_remove=cache_node_ids_to_remove,
            cache_node_ids_to_reboot=cache_node_ids_to_reboot,
        )
        self.cache_clusters[cache_cluster_id] = cache_cluster
        return cache_cluster

    @paginate(PAGINATION_MODEL)
    def describe_cache_clusters(
        self,
        cache_cluster_id: str,
        max_records: int,
        marker: str,
    ) -> List[CacheCluster]:
        if max_records is None:
            max_records = 100
        if cache_cluster_id:
            if cache_cluster_id in self.cache_clusters:
                cache_cluster = self.cache_clusters[cache_cluster_id]
                return list([cache_cluster])
            else:
                raise CacheClusterNotFound(cache_cluster_id)
        cache_clusters = list(self.cache_clusters.values())[:max_records]

        return cache_clusters

    def delete_cache_cluster(self, cache_cluster_id: str) -> CacheCluster:
        if cache_cluster_id:
            if cache_cluster_id in self.cache_clusters:
                cache_cluster = self.cache_clusters[cache_cluster_id]
                cache_cluster.cache_cluster_status = "deleting"
                return cache_cluster
        raise CacheClusterNotFound(cache_cluster_id)

    def create_cache_subnet_group(
        self,
        cache_subnet_group_name: str,
        cache_subnet_group_description: str,
        subnet_ids: List[str],
        tags: Optional[List[Dict[str, str]]],
    ) -> CacheSubnetGroup:
        if cache_subnet_group_name in self.cache_subnet_groups:
            raise CacheSubnetGroupAlreadyExists(cache_subnet_group_name)

        cache_subnet_group = CacheSubnetGroup(
            account_id=self.account_id,
            region_name=self.region_name,
            cache_subnet_group_name=cache_subnet_group_name,
            cache_subnet_group_description=cache_subnet_group_description,
            subnet_ids=subnet_ids,
            tags=tags,
        )
        self.cache_subnet_groups[cache_subnet_group_name] = cache_subnet_group
        return cache_subnet_group

    @paginate(PAGINATION_MODEL)
    def describe_cache_subnet_groups(
        self,
        cache_subnet_group_name: str,
    ) -> List[CacheSubnetGroup]:
        if cache_subnet_group_name:
            if cache_subnet_group_name in self.cache_subnet_groups:
                cache_subnet_group = self.cache_subnet_groups[cache_subnet_group_name]
                return list([cache_subnet_group])
            else:
                raise CacheSubnetGroupNotFound(cache_subnet_group_name)
        cache_subnet_groups = list(self.cache_subnet_groups.values())
        return cache_subnet_groups

    def list_tags_for_resource(self, arn: str) -> List[Dict[str, str]]:
        if self.arn_regex.match(arn):
            arn_breakdown = arn.split(":")
            resource_type = arn_breakdown[len(arn_breakdown) - 2]
            resource_name = arn_breakdown[len(arn_breakdown) - 1]
            if resource_type == "cluster":
                if resource_name in self.cache_clusters:
                    return self.cache_clusters[resource_name].get_tags()
            elif resource_type == "subnetgroup":
                if resource_name in self.cache_subnet_groups:
                    return self.cache_subnet_groups[resource_name].get_tags()
            else:
                return []
        else:
            raise InvalidARNFault(arn)
        return []


elasticache_backends = BackendDict(ElastiCacheBackend, "elasticache")

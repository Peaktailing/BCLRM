"""受理人路由：这堂课该找哪位管理员。

第一段的关键词是**指派**，不是**遴选**。

全库撮合（原来的「本人 → 本教研室 → 全院」）回答的是「哪里还有这东西」，
那是第二段的问题。第一段要回答的是「**这件事归谁管**」——它跟库存多少
无关，只跟课程/项目归属有关。两件事混在一起，就会出现这种怪现象：
教师申领时系统直接跳过本课的管理员去隔壁教研室拿了料，管理员全程不
知情，于是谁都不知道该去补货。

所以路由是配置，不是算法：查得到就照查，查不到就报错，绝不让系统自己
猜一个"看起来合适"的人。猜出来的受理人，事后没人认这个账。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Mapping, Optional

from domain.custody import Custodian
from domain.pipeline import TeacherRequest


class RoutingError(LookupError):
    """找不到受理人。

    必须显式失败：随便返回一个人会让「料从谁那出、谁该补」这条链断掉，
    而断掉的账本比空账本更危险。
    """


class CustodianRouter(ABC):
    """受理人路由抽象。"""

    @abstractmethod
    def route(self, request: TeacherRequest) -> Custodian:
        """给出这次申请的受理保管人；找不到抛 :class:`RoutingError`。"""

    @abstractmethod
    def describe(self) -> str:
        """规则说明（页面提示老师"这门课为什么找这个人"）。"""

    def candidates(self, request: TeacherRequest) -> tuple[Custodian, ...]:
        """可能受理的人（按优先级）。默认只有路由结果一个。"""
        try:
            return (self.route(request),)
        except RoutingError:
            return ()


class StaticRouter(CustodianRouter):
    """所有申请都归同一名保管人（单库房、演示、或小规模院系）。"""

    def __init__(self, custodian: Custodian) -> None:
        self.custodian = custodian

    def route(self, request: TeacherRequest) -> Custodian:
        return self.custodian

    def describe(self) -> str:
        return f"全部申请由 {self.custodian.describe()} 受理"


class SourceRouter(CustodianRouter):
    """按来源指派：课程名 / 实验项目 / 科研项目编号 → 保管人。

    BCLRM 里课程与管理员之间本来没有映射（``experiment_course`` 只有
    ``teacher``，没有 ``custodian``），这正是第一段一直缺位的根因。这里
    把映射做成数据（``custodian_route`` 表），而不是给业务表加列——因为
    同一套规则还要覆盖科研项目、教研室，加列加不完。
    """

    def __init__(
        self,
        rules: Mapping[str, Custodian],
        fallback: Optional[CustodianRouter] = None,
        label: str = "按课程/项目指派",
    ) -> None:
        self._rules = {str(key): value for key, value in rules.items()}
        self._fallback = fallback
        self._label = label

    def route(self, request: TeacherRequest) -> Custodian:
        matched = self._lookup(request.source_code)
        if matched is not None:
            return matched
        if self._fallback is not None:
            return self._fallback.route(request)
        raise RoutingError(
            f"没有为「{request.source_code or request.sheet.title}」指派受理管理员"
            "——请先在「保管人路由」里配上这门课归谁管"
        )

    def candidates(self, request: TeacherRequest) -> tuple[Custodian, ...]:
        matched = self._lookup(request.source_code)
        if matched is not None:
            rest = self._fallback.candidates(request) if self._fallback else ()
            return (matched,) + tuple(c for c in rest if not c.same_as(matched))
        if self._fallback is not None:
            return self._fallback.candidates(request)
        return ()

    def _lookup(self, code: str) -> Optional[Custodian]:
        """两级匹配：先整键，再退到课程名（``课程/班级`` 的前半）。

        一门课通常由同一个管理员管，但同一个老师教多个班时，班级之间
        也可能分给不同的人。所以先试精确键，再退到课程级规则——两种
        粒度都能配，不必为"要不要带班级"做一锤子决定。
        """
        if not code:
            return None
        if code in self._rules:
            return self._rules[code]
        course = code.split("/")[0]
        return self._rules.get(course)

    def describe(self) -> str:
        tail = f"；兜底：{self._fallback.describe()}" if self._fallback else "；无兜底"
        return f"{self._label}（{len(self._rules)} 条规则）{tail}"


class DepartmentRouter(CustodianRouter):
    """按申请人所属科室指派（课程没单独配人时的兜底）。

    ``department_of`` 是个函数而不是映射表：人员的科室在 ``person`` 表里
    随时会变，路由不该缓存一份可能过期的副本。
    """

    def __init__(
        self,
        department_of: Callable[[str], str],
        mapping: Mapping[str, Custodian],
        fallback: Optional[Custodian] = None,
    ) -> None:
        self._department_of = department_of
        self._mapping = {str(key): value for key, value in mapping.items()}
        self._fallback = fallback

    def route(self, request: TeacherRequest) -> Custodian:
        department = (self._department_of(request.requester_name) or "").strip()
        if department and department in self._mapping:
            return self._mapping[department]
        if self._fallback is not None:
            return self._fallback
        raise RoutingError(
            f"「{request.requester_name}」所属科室"
            f"（{department or '未登记'}）没有对应的受理管理员"
        )

    def describe(self) -> str:
        tail = f"；兜底：{self._fallback.describe()}" if self._fallback else ""
        return f"按申请人科室指派（{len(self._mapping)} 个科室）{tail}"


class CompositeRouter(CustodianRouter):
    """依次尝试多个路由，第一个能给出答案的胜出。

    典型组合：课程指派 → 科室指派 → 超管兜底。顺序即优先级，且**每一层
    都必须是明确配置的**，不存在"猜"。
    """

    def __init__(self, *routers: CustodianRouter) -> None:
        self._routers = tuple(routers)

    def route(self, request: TeacherRequest) -> Custodian:
        errors: list[str] = []
        for router in self._routers:
            try:
                return router.route(request)
            except RoutingError as exc:
                errors.append(str(exc))
        raise RoutingError("；".join(errors) or "没有任何可用的受理人路由")

    def candidates(self, request: TeacherRequest) -> tuple[Custodian, ...]:
        found: list[Custodian] = []
        for router in self._routers:
            for custodian in router.candidates(request):
                if not any(custodian.same_as(existing) for existing in found):
                    found.append(custodian)
        return tuple(found)

    def describe(self) -> str:
        if not self._routers:
            return "未配置任何路由"
        return " → ".join(router.describe() for router in self._routers)


__all__ = [
    "RoutingError",
    "CustodianRouter",
    "StaticRouter",
    "SourceRouter",
    "DepartmentRouter",
    "CompositeRouter",
]

"""统一错误处理模块

提供试剂管理系统的统一错误处理机制，包括：
- 自定义异常类层次结构
- 错误日志记录器
- 业务结果包装类
- 统一异常捕获装饰器

所有业务代码应使用本模块提供的异常类和结果包装类，
禁止使用 print 输出错误信息。
"""

import logging
import os
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Generic

# ============================================================================
# 自定义异常类
# ============================================================================

class ReagentException(Exception):
    """试剂管理系统基础异常类
    
    所有自定义业务异常的基类，提供统一的异常信息格式和错误码。
    
    Attributes:
        message: 异常描述信息
        error_code: 错误码，用于分类异常类型
        details: 异常详细信息字典
    """
    
    def __init__(self, message: str, error_code: str = "UNKNOWN_ERROR", details: Optional[dict] = None):
        """初始化基础异常
        
        Args:
            message: 异常描述信息
            error_code: 错误码，默认为 UNKNOWN_ERROR
            details: 异常详细信息字典，默认为 None
        """
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """返回异常的字符串表示"""
        base = f"[{self.error_code}] {self.message}"
        if self.details:
            base += f" - 详情: {self.details}"
        return base
    
    def to_dict(self) -> dict:
        """将异常转换为字典格式
        
        Returns:
            包含异常信息的字典
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


class ValidationError(ReagentException):
    """参数校验异常
    
    用于参数验证失败的场景，如必填项缺失、格式错误、值越界等。
    
    Examples:
        >>> raise ValidationError("试剂名称不能为空", error_code="EMPTY_REAGENT_NAME")
        >>> raise ValidationError("数量必须大于0", error_code="INVALID_QUANTITY", details={"value": -1})
    """
    
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR", details: Optional[dict] = None):
        """初始化参数校验异常
        
        Args:
            message: 校验失败描述信息
            error_code: 错误码，默认为 VALIDATION_ERROR
            details: 校验失败详细信息字典
        """
        super().__init__(message, error_code, details)


class DatabaseError(ReagentException):
    """数据库操作异常
    
    用于数据库操作失败的场景，如连接失败、查询错误、写入失败等。
    
    Examples:
        >>> raise DatabaseError("数据库连接超时", error_code="DB_CONNECTION_TIMEOUT")
        >>> raise DatabaseError("记录创建失败", error_code="DB_CREATE_FAILED", details={"table": "reagent_bottle"})
    """
    
    def __init__(self, message: str, error_code: str = "DATABASE_ERROR", details: Optional[dict] = None):
        """初始化数据库操作异常
        
        Args:
            message: 数据库操作失败描述信息
            error_code: 错误码，默认为 DATABASE_ERROR
            details: 数据库操作详细信息字典
        """
        super().__init__(message, error_code, details)


class NotFoundError(ReagentException):
    """资源未找到异常
    
    用于查询资源不存在的场景。
    """
    
    def __init__(self, message: str, error_code: str = "NOT_FOUND", details: Optional[dict] = None):
        """初始化资源未找到异常
        
        Args:
            message: 资源未找到描述信息
            error_code: 错误码，默认为 NOT_FOUND
            details: 详细信息字典
        """
        super().__init__(message, error_code, details)


# ============================================================================
# 错误日志记录器
# ============================================================================

class ErrorLogger:
    """错误日志记录器
    
    统一的日志记录类，支持控制台输出和文件输出，
    禁止使用 print 输出错误信息。
    
    采用单例模式，确保全局只有一个日志实例。
    
    Attributes:
        logger: Python logging 模块的 logger 实例
    """
    
    _instance = None
    _initialized = False
    
    DEFAULT_LOG_DIR = "logs"
    DEFAULT_LOG_FILE = "error.log"
    DEFAULT_LOG_LEVEL = logging.INFO
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, log_dir: Optional[str] = None, log_file: Optional[str] = None, 
                 log_level: int = None, name: str = "reagent_manager"):
        """初始化日志记录器
        
        Args:
            log_dir: 日志文件目录，默认为 logs/
            log_file: 日志文件名，默认为 error.log
            log_level: 日志级别，默认为 INFO
            name: logger 名称
        """
        if self._initialized:
            return
        
        self._initialized = True
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level or self.DEFAULT_LOG_LEVEL)
        self.logger.propagate = False
        
        # 避免重复添加 handler
        if self.logger.handlers:
            return
        
        log_dir = log_dir or self.DEFAULT_LOG_DIR
        log_file = log_file or self.DEFAULT_LOG_FILE
        
        # 确保日志目录存在
        self._ensure_log_dir(log_dir)
        
        # 创建 formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 控制台 handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level or self.DEFAULT_LOG_LEVEL)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件 handler
        log_path = os.path.join(log_dir, log_file)
        try:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.WARNING)  # 文件只记录 WARNING 及以上
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except (OSError, IOError):
            # 文件日志创建失败时不报错，仅使用控制台
            pass
    
    def _ensure_log_dir(self, log_dir: str) -> None:
        """确保日志目录存在
        
        Args:
            log_dir: 日志目录路径
        """
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except OSError:
            # 目录创建失败时静默处理，使用控制台日志
            pass
    
    def debug(self, message: str, **kwargs) -> None:
        """记录 DEBUG 级别日志
        
        Args:
            message: 日志消息
            **kwargs: 额外的上下文字段
        """
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        full_msg = f"{message} | {extra}" if extra else message
        self.logger.debug(full_msg)
    
    def info(self, message: str, **kwargs) -> None:
        """记录 INFO 级别日志
        
        Args:
            message: 日志消息
            **kwargs: 额外的上下文字段
        """
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        full_msg = f"{message} | {extra}" if extra else message
        self.logger.info(full_msg)
    
    def warning(self, message: str, **kwargs) -> None:
        """记录 WARNING 级别日志
        
        Args:
            message: 日志消息
            **kwargs: 额外的上下文字段
        """
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        full_msg = f"{message} | {extra}" if extra else message
        self.logger.warning(full_msg)
    
    def error(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """记录 ERROR 级别日志
        
        Args:
            message: 日志消息
            exception: 异常对象，若提供则记录堆栈信息
            **kwargs: 额外的上下文字段
        """
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        full_msg = f"{message} | {extra}" if extra else message
        
        if exception is not None:
            tb_str = traceback.format_exc()
            full_msg = f"{full_msg}\n异常堆栈:\n{tb_str}"
        
        self.logger.error(full_msg)
    
    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """记录 CRITICAL 级别日志
        
        Args:
            message: 日志消息
            exception: 异常对象，若提供则记录堆栈信息
            **kwargs: 额外的上下文字段
        """
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        full_msg = f"{message} | {extra}" if extra else message
        
        if exception is not None:
            tb_str = traceback.format_exc()
            full_msg = f"{full_msg}\n异常堆栈:\n{tb_str}"
        
        self.logger.critical(full_msg)
    
    def log_exception(self, exception: Exception, context: str = "", level: int = logging.ERROR) -> None:
        """记录异常信息
        
        Args:
            exception: 异常对象
            context: 上下文描述
            level: 日志级别
        """
        prefix = f"[{context}] " if context else ""
        if isinstance(exception, ReagentException):
            message = f"{prefix}{exception}"
        else:
            message = f"{prefix}{type(exception).__name__}: {str(exception)}"
        
        if level == logging.ERROR:
            self.error(message, exception=exception)
        elif level == logging.WARNING:
            self.warning(message)
        elif level == logging.CRITICAL:
            self.critical(message, exception=exception)
        else:
            self.info(message)


# 全局日志实例
logger = ErrorLogger()


# ============================================================================
# 业务结果包装类
# ============================================================================

T = TypeVar('T')

class ServiceResult(Generic[T]):
    """业务结果包装类
    
    统一封装业务方法的返回结果，包含成功标志、消息和数据。
    
    Attributes:
        success: 操作是否成功
        message: 结果描述信息
        data: 操作返回的数据
        error_code: 错误码（失败时有效）
        timestamp: 结果生成时间戳
    """
    
    def __init__(self, success: bool, message: str = "", data: T = None, 
                 error_code: str = ""):
        """初始化业务结果
        
        Args:
            success: 操作是否成功
            message: 结果描述信息
            data: 操作返回的数据
            error_code: 错误码（失败时有效）
        """
        self.success = success
        self.message = message
        self.data = data
        self.error_code = error_code
        self.timestamp = datetime.now().isoformat()
    
    @classmethod
    def ok(cls, data: T = None, message: str = "操作成功") -> "ServiceResult[T]":
        """创建成功结果
        
        Args:
            data: 成功返回的数据
            message: 成功描述信息
            
        Returns:
            成功的 ServiceResult 实例
        """
        return cls(success=True, message=message, data=data)
    
    @classmethod
    def fail(cls, message: str, error_code: str = "UNKNOWN_ERROR", 
             data: Any = None) -> "ServiceResult[T]":
        """创建失败结果
        
        Args:
            message: 失败描述信息
            error_code: 错误码
            data: 附加数据
            
        Returns:
            失败的 ServiceResult 实例
        """
        return cls(success=False, message=message, data=data, error_code=error_code)
    
    @classmethod
    def from_exception(cls, exception: Exception) -> "ServiceResult[T]":
        """从异常创建失败结果
        
        Args:
            exception: 异常对象
            
        Returns:
            失败的 ServiceResult 实例
        """
        if isinstance(exception, ReagentException):
            return cls(
                success=False,
                message=exception.message,
                error_code=exception.error_code,
                data=exception.details
            )
        else:
            return cls(
                success=False,
                message=str(exception),
                error_code="UNKNOWN_ERROR"
            )
    
    def is_success(self) -> bool:
        """判断操作是否成功
        
        Returns:
            True 表示成功，False 表示失败
        """
        return self.success
    
    def is_failure(self) -> bool:
        """判断操作是否失败
        
        Returns:
            True 表示失败，False 表示成功
        """
        return not self.success
    
    def get_or_raise(self) -> T:
        """获取数据，失败则抛出异常
        
        Returns:
            成功时返回 data
            
        Raises:
            ReagentException: 操作失败时抛出
        """
        if self.is_failure():
            raise ReagentException(
                message=self.message,
                error_code=self.error_code,
                details=self.data if isinstance(self.data, dict) else None
            )
        return self.data
    
    def to_dict(self) -> dict:
        """转换为字典
        
        Returns:
            包含结果信息的字典
        """
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error_code": self.error_code,
            "timestamp": self.timestamp
        }
    
    def __str__(self) -> str:
        """返回结果的字符串表示"""
        status = "成功" if self.success else "失败"
        base = f"[操作{status}] {self.message}"
        if self.error_code:
            base += f" (错误码: {self.error_code})"
        return base


# ============================================================================
# 统一异常捕获装饰器
# ============================================================================

def handle_exception(log_errors: bool = True, return_result: bool = True, 
                     context: str = ""):
    """统一异常捕获装饰器
    
    自动捕获被装饰函数中的异常，记录日志，并可选择返回 ServiceResult。
    
    Args:
        log_errors: 是否记录错误日志，默认为 True
        return_result: 是否返回 ServiceResult 包装的结果，默认为 True
                       若为 False，则异常会被重新抛出
        context: 上下文描述，用于日志记录
    
    Returns:
        装饰器函数
    
    Examples:
        >>> @handle_exception(context="试剂入库")
        ... def add_reagent(data):
        ...     # 业务逻辑
        ...     return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            ctx = context or func.__name__
            try:
                result = func(*args, **kwargs)
                return result
            except ReagentException as e:
                # 自定义业务异常
                if log_errors:
                    logger.log_exception(e, context=ctx, level=logging.WARNING)
                if return_result:
                    return ServiceResult.from_exception(e)
                raise
            except (ValueError, TypeError) as e:
                # 参数类型错误转换为 ValidationError
                ve = ValidationError(
                    message=f"参数错误: {str(e)}",
                    error_code="PARAM_TYPE_ERROR",
                    details={"func": func.__name__, "args": str(args), "kwargs": str(kwargs)}
                )
                if log_errors:
                    logger.log_exception(ve, context=ctx, level=logging.WARNING)
                if return_result:
                    return ServiceResult.from_exception(ve)
                raise ve
            except Exception as e:
                # 其他未知异常
                err = ReagentException(
                    message=f"系统异常: {str(e)}",
                    error_code="SYSTEM_ERROR",
                    details={"func": func.__name__}
                )
                if log_errors:
                    logger.log_exception(e, context=ctx, level=logging.ERROR)
                if return_result:
                    return ServiceResult.from_exception(err)
                raise err
        return wrapper
    return decorator


def validate_params(validation_func: Callable[..., Optional[ValidationError]]):
    """参数校验装饰器
    
    在执行函数前先执行参数校验函数，校验失败则抛出 ValidationError。
    
    Args:
        validation_func: 参数校验函数，接收相同的参数，返回 None 或 ValidationError
    
    Returns:
        装饰器函数
    
    Examples:
        >>> def _check_params(name, quantity):
        ...     if not name:
        ...         return ValidationError("名称不能为空")
        ...     if quantity <= 0:
        ...         return ValidationError("数量必须大于0")
        ...     return None
        ...
        >>> @validate_params(_check_params)
        ... def add_reagent(name, quantity):
        ...     # 业务逻辑
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            error = validation_func(*args, **kwargs)
            if error is not None:
                logger.warning(f"参数校验失败: {error}", func=func.__name__)
                raise error
            return func(*args, **kwargs)
        return wrapper
    return decorator

#ifndef DARLING_PLATFORM_PORT_H
#define DARLING_PLATFORM_PORT_H

#include <TargetConditionals.h>
#include "platform/arm64_syscall.h"

#if defined(__x86_64__) || defined(__i386__)
#  define DARLING_ARCH_X86 1
#elif defined(__aarch64__) || (defined(__arm64__) && !defined(DARLING_FORCE_AARCH64))
#  define DARLING_ARCH_ARM64 1
#else
#  warning "Unknown architecture - syscall forwarding may not work correctly"
#endif

#if DARLING_ARCH_ARM64
#  define ARCH_SYSCALL_NUMBER(X) (X) /* X16 holds syscall nr */
#  define ARCH_THREAD_CTX_FP    "tpidrro_el0"
#else
#  define ARCH_SYSCALL_NUMBER(X) (X) /* X8 holds syscall nr */
#  define ARCH_THREAD_CTX_FP    "gpr"
#endif

#endif /* DARLING_PLATFORM_PORT_H */

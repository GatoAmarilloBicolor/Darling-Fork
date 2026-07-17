#ifndef DARLING_PLATFORM_ARM64_SYSCALL_H
#define DARLING_PLATFORM_ARM64_SYSCALL_H

#include <stdint.h>
#include <sys/syscall.h>

enum {
    SYS_CLASS_MACH   = 0,
    SYS_CLASS_BSD    = 1,
    SYS_CLASS_MD     = 2
};

static inline __attribute__((always_inline))
unsigned long arm64_bsd_to_linux(unsigned int bsd_nr)
{
    return (unsigned long)(bsd_nr - 0x1b5a6);
}

static inline __attribute__((always_inline))
unsigned long mach_to_linux(unsigned int mach_nr)
{
    return (unsigned long)(mach_nr + 0x1b5a6);
}

#endif /* DARLING_PLATFORM_ARM64_SYSCALL_H */

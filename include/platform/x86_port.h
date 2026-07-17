#ifndef DARLING_PLATFORM_X86_PORT_H
#define DARLINGplatform_port_HDR

#include <stdint.h>
#include "port.h"

#if !DARLING_ARCH_X86
#error "x86 port requires x86 architecture"
#endif

/* Darwin x86 syscall class mapping */
enum {
    DARLING_X86_MAC = 0,
    DARLING_X86_BSD = 1,
    DARLING_X86_MD  =2
};

static inline __attribute__((always_inline))
unsigned long darling_x86_class_decode(unsigned char class, unsigned int syscall_nr)
{
    switch (class) {
        case DARLING_X86_MAC: return syscall_nr;
        case DARLING_X86_BSD: return arm64_bsd_to_linux((unsigned int)(syscall_nr - 0x1b5a6) );
        case DARLING_X86_MD: return syscall_nr;
    }
    return syscall_nr;
}

#endif /* DARLING_PLATFORM_X86_PORT_H */

#import <Foundation/Foundation.h>
#include <sys/types.h>
#include <sys/sysctl.h>

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        size_t size;
        sysctlbyname("hw.machine", NULL, &size, NULL, 0);
        char *machine = malloc(size);
        sysctlbyname("hw.machine", machine, &size, NULL, 0);
        
        sysctlbyname("hw.model", NULL, &size, NULL, 0);
        char *model = malloc(size);
        sysctlbyname("hw.model", model, &size, NULL, 0);

        printf("Darling CPU Info:\n");
        printf("Machine: %s\n", machine);
        printf("Model: %s\n", model);
        
        free(machine);
        free(model);
    }
    return 0;
}

/*
 * Standalone Liblinphone SDK discovery helper.
 *
 * SPDX-License-Identifier: MIT
 *
 * This is a separate executable, not linked into QEMU. It does not
 * instantiate a LinphoneCore, load accounts, or start network services.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linphone/linphonecore.h>

int main(int argc, char **argv)
{
    const char *version;

    if (argc != 2 || strcmp(argv[1], "--version") != 0) {
        fprintf(stderr, "Usage: %s --version\n", argv[0]);
        return EXIT_FAILURE;
    }

    version = linphone_core_get_version();
    if (!version || !version[0]) {
        fputs("Liblinphone returned no SDK version.\n", stderr);
        return EXIT_FAILURE;
    }
    printf("Liblinphone %s\n", version);
    return EXIT_SUCCESS;
}

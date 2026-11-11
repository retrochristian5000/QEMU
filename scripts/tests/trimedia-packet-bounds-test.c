/* Exact-size allocation tests, including all partial packet lengths.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "packet.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#if defined(NDEBUG)
#error "Assertions must stay enabled in TriMedia bounds regressions"
#endif

int main(void)
{
    unsigned int cases = 0;
    for (unsigned int fmt = 0; fmt < 1024; ++fmt) {
        unsigned int required = 2, count = 0;
        for (unsigned int slot = 0; slot < 5; ++slot) {
            unsigned int code = (fmt >> (slot * 2)) & 3;
            if (code != 3) {
                ++count;
                required += 3 + code;
            }
        }
        required += count > 3;
        assert(required <= TRIMEDIA_PACKET_MAX_BYTES);
        /* One allocation for each exact byte count: ASan can see the
         * redzone immediately after the advertised readable buffer. */
        for (unsigned int available = 0;
             available <= TRIMEDIA_PACKET_MAX_BYTES; ++available) {
            uint8_t *bytes = malloc(available ? available : 1);
            TrimediaPacketLayout p;
            bool ok;

            assert(bytes != NULL);
            for (unsigned int i = 0; i < available; ++i) {
                bytes[i] = (uint8_t)(i * 17 + fmt);
            }
            ok = trimedia_unpack_packet(bytes, available, (uint16_t)fmt, &p);
            assert(ok == (available >= required));
            if (ok) {
                assert(p.encoded_size == required);
                assert(p.num_ops == count);
                assert(p.following_format ==
                       ((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8)));
            } else {
                assert(p.encoded_size == 0 && p.num_ops == 0);
            }
            ++cases;
            free(bytes);
        }
    }
    assert(cases == 1024 * (TRIMEDIA_PACKET_MAX_BYTES + 1));
    printf("TriMedia exact-size boundaries: %u cases PASS\n", cases);
    return 0;
}

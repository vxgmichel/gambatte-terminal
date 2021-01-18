
#include "gambatte.h"

namespace gambatte {
    class GetInput : public InputGetter {
        public:
            unsigned value;
            virtual unsigned operator()() { return value; }
    };
}

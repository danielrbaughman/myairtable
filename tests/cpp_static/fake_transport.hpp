#pragma once

// Scripted offline transport for client tests (C# FakeTransport parity):
// records every request and replays a queue of responses / failures.
#include <deque>
#include <functional>
#include <memory>
#include <variant>
#include <vector>

#include "curl_transport.hpp"

namespace myairtable_tests {

class FakeTransport {
  public:
    using Step = std::variant<myairtable::HttpResponse, myairtable::TransportFailure>;

    FakeTransport() : state_(std::make_shared<State>()) {}

    /// Queue a plain response.
    FakeTransport& respond(int status, std::string body = "{}",
                           std::map<std::string, std::string> headers = {}) {
        state_->steps.push_back(
            myairtable::HttpResponse{status, std::move(body), std::move(headers)});
        return *this;
    }

    /// Queue a transport-level failure (DNS/reset/timeout).
    FakeTransport& fail(std::string message = "connection reset") {
        state_->steps.push_back(myairtable::TransportFailure{std::move(message)});
        return *this;
    }

    const std::vector<myairtable::HttpRequest>& requests() const { return state_->requests; }
    size_t calls() const { return state_->requests.size(); }

    /// The transport functor handed to AirtableClient (copyable; shared state).
    myairtable::Transport fn() {
        auto state = state_;
        return [state](const myairtable::HttpRequest& request) -> myairtable::HttpResponse {
            state->requests.push_back(request);
            if (state->steps.empty()) {
                return myairtable::HttpResponse{200, "{}", {}};
            }
            Step step = std::move(state->steps.front());
            state->steps.pop_front();
            if (auto* failure = std::get_if<myairtable::TransportFailure>(&step)) {
                throw *failure;
            }
            return std::get<myairtable::HttpResponse>(step);
        };
    }

  private:
    struct State {
        std::deque<Step> steps;
        std::vector<myairtable::HttpRequest> requests;
    };
    std::shared_ptr<State> state_;
};

} // namespace myairtable_tests

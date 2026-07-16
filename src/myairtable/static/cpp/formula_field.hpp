#pragma once

#include <string>
#include <utility>

namespace myairtable {

/// Base for the generated per-field filter builders: wraps a field id and
/// renders `{fieldId}` references.
class FormulaField {
  public:
    explicit FormulaField(std::string field_id) : field_id_(std::move(field_id)) {}
    virtual ~FormulaField() = default;

    const std::string& field_id() const { return field_id_; }

    std::string field() const { return "{" + field_id_ + "}"; }

    virtual std::string is_empty() const { return field() + "=BLANK()"; }

    virtual std::string is_not_empty() const { return field() + "!=BLANK()"; }

  private:
    std::string field_id_;
};

} // namespace myairtable

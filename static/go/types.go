package airtable

// Plain data carriers for Airtable's complex field types and the record
// envelope, plus sort specs and the view interface.

// Record is the API record envelope: {"id": "...", "createdTime": "...", "fields": {...}}.
type Record[T any] struct {
	ID          string        `json:"id"`
	CreatedTime *AirtableTime `json:"createdTime,omitempty"`
	Fields      T             `json:"fields"`
}

// AirtableAttachment is an attachment object as returned by the API. For
// uploads, only URL (and optionally Filename) need be set.
type AirtableAttachment struct {
	ID         string              `json:"id,omitempty"`
	URL        string              `json:"url,omitempty"`
	Filename   string              `json:"filename,omitempty"`
	Size       *int64              `json:"size,omitempty"`
	Type       string              `json:"type,omitempty"`
	Thumbnails *AirtableThumbnails `json:"thumbnails,omitempty"`
}

// AirtableThumbnails holds the generated thumbnail variants for an attachment.
type AirtableThumbnails struct {
	Small *Thumbnail `json:"small,omitempty"`
	Large *Thumbnail `json:"large,omitempty"`
	Full  *Thumbnail `json:"full,omitempty"`
}

// Thumbnail is a single thumbnail variant.
type Thumbnail struct {
	URL    string `json:"url"`
	Width  *int64 `json:"width,omitempty"`
	Height *int64 `json:"height,omitempty"`
}

// AirtableCollaborator is a user/collaborator field value.
type AirtableCollaborator struct {
	ID            string `json:"id,omitempty"`
	Email         string `json:"email,omitempty"`
	Name          string `json:"name,omitempty"`
	ProfilePicURL string `json:"profilePicUrl,omitempty"`
}

// AirtableButton is a button field value.
type AirtableButton struct {
	Label string `json:"label,omitempty"`
	URL   string `json:"url,omitempty"`
}

// SortDirection is the direction of a sort spec ("asc" / "desc").
type SortDirection string

const (
	SortAsc  SortDirection = "asc"
	SortDesc SortDirection = "desc"
)

// Sort is a single field sort specification.
type Sort struct {
	Field     string        `json:"field"`
	Direction SortDirection `json:"direction"`
}

// View is implemented by the generated per-table view constant types, exposing
// the view's Airtable ID for use in queries.
type View interface {
	ViewID() string
}

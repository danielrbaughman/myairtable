# from rogoat import (
#     BarcodeTypesKeys,
#     BonusesFinesKeys,
#     BonusPeriodsKeys,
#     BoxKeys,
#     BoxShipmentsKeys,
#     BranchesKeys,
#     ChemFillupKeys,
#     ChemRigProductsKeys,
#     CompaniesKeys,
#     ContactsKeys,
#     CourierPickupsKeys,
#     CrmBasePartitionsKeys,
#     CustomerStepsKeys,
#     DealsKeys,
#     DropoffsKeys,
#     EditFormsKeys,
#     EventsKeys,
#     FinesKeys,
#     GrowersKeys,
#     JobReadyKeys,
#     JobsKeys,
#     LabsKeys,
#     LabTestsKeys,
#     MeetingsKeys,
#     OldEndOfShiftIssueReportKeys,
#     OldInspectionsKeys,
#     OldIssuesKeys,
#     QuoteInvoiceKeys,
#     RigsKeys,
#     RobotKeys,
#     ShiftDropoffsKeys,
#     ShiftsKeys,
#     ShiftTimesKeys,
#     SourcesKeys,
#     TeamKeys,
# )

# from .formula import *  # noqa: F403
# from .formula import (
#     AttachmentsField,
#     BooleanField,
#     DateField,
#     NumberField,
#     TextField,
#     TextListField,
# )


# def _validate_key(name, key_enum):
#     if name not in key_enum.__args__:
#         raise ValueError(f"Invalid field name: {name}.")


# # region Jobs
# class JobsTextField(TextField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# class JobsTextListField(TextListField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# class JobsNumberField(NumberField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# class JobsBooleanField(BooleanField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# class JobsAttachmentsField(AttachmentsField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# class JobsDateField(DateField):
#     def __init__(self, name: JobsKeys):
#         _validate_key(name, JobsKeys)
#         super().__init__(name=name)


# # endregion


# # region Deals
# class DealsTextField(TextField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# class DealsTextListField(TextListField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# class DealsNumberField(NumberField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# class DealsBooleanField(BooleanField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# class DealsAttachmentsField(AttachmentsField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# class DealsDateField(DateField):
#     def __init__(self, name: DealsKeys):
#         _validate_key(name, DealsKeys)
#         super().__init__(name=name)


# # endregion


# # region Contacts
# class ContactsTextField(TextField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# class ContactsTextListField(TextListField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# class ContactsNumberField(NumberField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# class ContactsBooleanField(BooleanField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# class ContactsAttachmentsField(AttachmentsField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# class ContactsDateField(DateField):
#     def __init__(self, name: ContactsKeys):
#         _validate_key(name, ContactsKeys)
#         super().__init__(name=name)


# # endregion


# # region Companies
# class CompaniesTextField(TextField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# class CompaniesTextListField(TextListField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# class CompaniesNumberField(NumberField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# class CompaniesBooleanField(BooleanField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# class CompaniesAttachmentsField(AttachmentsField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# class CompaniesDateField(DateField):
#     def __init__(self, name: CompaniesKeys):
#         _validate_key(name, CompaniesKeys)
#         super().__init__(name=name)


# # endregion


# # region Meetings
# class MeetingsTextField(TextField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# class MeetingsTextListField(TextListField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# class MeetingsNumberField(NumberField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# class MeetingsBooleanField(BooleanField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# class MeetingsAttachmentsField(AttachmentsField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# class MeetingsDateField(DateField):
#     def __init__(self, name: MeetingsKeys):
#         _validate_key(name, MeetingsKeys)
#         super().__init__(name=name)


# # endregion


# # region Events
# class EventsTextField(TextField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# class EventsTextListField(TextListField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# class EventsNumberField(NumberField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# class EventsBooleanField(BooleanField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# class EventsAttachmentsField(AttachmentsField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# class EventsDateField(DateField):
#     def __init__(self, name: EventsKeys):
#         _validate_key(name, EventsKeys)
#         super().__init__(name=name)


# # endregion


# # region Branches
# class BranchesTextField(TextField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# class BranchesTextListField(TextListField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# class BranchesNumberField(NumberField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# class BranchesBooleanField(BooleanField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# class BranchesAttachmentsField(AttachmentsField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# class BranchesDateField(DateField):
#     def __init__(self, name: BranchesKeys):
#         _validate_key(name, BranchesKeys)
#         super().__init__(name=name)


# # endregion


# # region QuoteInvoice
# class QuoteInvoiceTextField(TextField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# class QuoteInvoiceTextListField(TextListField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# class QuoteInvoiceNumberField(NumberField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# class QuoteInvoiceBooleanField(BooleanField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# class QuoteInvoiceAttachmentsField(AttachmentsField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# class QuoteInvoiceDateField(DateField):
#     def __init__(self, name: QuoteInvoiceKeys):
#         _validate_key(name, QuoteInvoiceKeys)
#         super().__init__(name=name)


# # endregion


# # region JobReady
# class JobReadyTextField(TextField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# class JobReadyTextListField(TextListField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# class JobReadyNumberField(NumberField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# class JobReadyBooleanField(BooleanField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# class JobReadyAttachmentsField(AttachmentsField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# class JobReadyDateField(DateField):
#     def __init__(self, name: JobReadyKeys):
#         _validate_key(name, JobReadyKeys)
#         super().__init__(name=name)


# # endregion


# # region Box
# class BoxTextField(TextField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# class BoxTextListField(TextListField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# class BoxNumberField(NumberField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# class BoxBooleanField(BooleanField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# class BoxAttachmentsField(AttachmentsField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# class BoxDateField(DateField):
#     def __init__(self, name: BoxKeys):
#         _validate_key(name, BoxKeys)
#         super().__init__(name=name)


# # endregion


# # region BoxShipments
# class BoxShipmentsTextField(TextField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# class BoxShipmentsTextListField(TextListField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# class BoxShipmentsNumberField(NumberField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# class BoxShipmentsBooleanField(BooleanField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# class BoxShipmentsAttachmentsField(AttachmentsField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# class BoxShipmentsDateField(DateField):
#     def __init__(self, name: BoxShipmentsKeys):
#         _validate_key(name, BoxShipmentsKeys)
#         super().__init__(name=name)


# # endregion


# # region CourierPickups
# class CourierPickupsTextField(TextField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# class CourierPickupsTextListField(TextListField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# class CourierPickupsNumberField(NumberField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# class CourierPickupsBooleanField(BooleanField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# class CourierPickupsAttachmentsField(AttachmentsField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# class CourierPickupsDateField(DateField):
#     def __init__(self, name: CourierPickupsKeys):
#         _validate_key(name, CourierPickupsKeys)
#         super().__init__(name=name)


# # endregion


# # region Dropoffs
# class DropoffsTextField(TextField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# class DropoffsTextListField(TextListField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# class DropoffsNumberField(NumberField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# class DropoffsBooleanField(BooleanField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# class DropoffsAttachmentsField(AttachmentsField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# class DropoffsDateField(DateField):
#     def __init__(self, name: DropoffsKeys):
#         _validate_key(name, DropoffsKeys)
#         super().__init__(name=name)


# # endregion


# # region Shifts
# class ShiftsTextField(TextField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# class ShiftsTextListField(TextListField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# class ShiftsNumberField(NumberField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# class ShiftsBooleanField(BooleanField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# class ShiftsAttachmentsField(AttachmentsField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# class ShiftsDateField(DateField):
#     def __init__(self, name: ShiftsKeys):
#         _validate_key(name, ShiftsKeys)
#         super().__init__(name=name)


# # endregion


# # region ShiftTimes
# class ShiftTimesTextField(TextField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# class ShiftTimesTextListField(TextListField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# class ShiftTimesNumberField(NumberField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# class ShiftTimesBooleanField(BooleanField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# class ShiftTimesAttachmentsField(AttachmentsField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# class ShiftTimesDateField(DateField):
#     def __init__(self, name: ShiftTimesKeys):
#         _validate_key(name, ShiftTimesKeys)
#         super().__init__(name=name)


# # endregion


# # region ShiftDropoffs
# class ShiftDropoffsTextField(TextField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# class ShiftDropoffsTextListField(TextListField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# class ShiftDropoffsNumberField(NumberField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# class ShiftDropoffsBooleanField(BooleanField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# class ShiftDropoffsAttachmentsField(AttachmentsField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# class ShiftDropoffsDateField(DateField):
#     def __init__(self, name: ShiftDropoffsKeys):
#         _validate_key(name, ShiftDropoffsKeys)
#         super().__init__(name=name)


# # endregion


# # region Labs
# class LabsTextField(TextField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# class LabsTextListField(TextListField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# class LabsNumberField(NumberField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# class LabsBooleanField(BooleanField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# class LabsAttachmentsField(AttachmentsField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# class LabsDateField(DateField):
#     def __init__(self, name: LabsKeys):
#         _validate_key(name, LabsKeys)
#         super().__init__(name=name)


# # endregion


# # region LabTests
# class LabTestsTextField(TextField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# class LabTestsTextListField(TextListField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# class LabTestsNumberField(NumberField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# class LabTestsBooleanField(BooleanField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# class LabTestsAttachmentsField(AttachmentsField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# class LabTestsDateField(DateField):
#     def __init__(self, name: LabTestsKeys):
#         _validate_key(name, LabTestsKeys)
#         super().__init__(name=name)


# # endregion


# # region Growers
# class GrowersTextField(TextField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# class GrowersTextListField(TextListField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# class GrowersNumberField(NumberField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# class GrowersBooleanField(BooleanField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# class GrowersAttachmentsField(AttachmentsField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# class GrowersDateField(DateField):
#     def __init__(self, name: GrowersKeys):
#         _validate_key(name, GrowersKeys)
#         super().__init__(name=name)


# # endregion


# # region Robot
# class RobotTextField(TextField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# class RobotTextListField(TextListField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# class RobotNumberField(NumberField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# class RobotBooleanField(BooleanField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# class RobotAttachmentsField(AttachmentsField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# class RobotDateField(DateField):
#     def __init__(self, name: RobotKeys):
#         _validate_key(name, RobotKeys)
#         super().__init__(name=name)


# # endregion


# # region Rigs
# class RigsTextField(TextField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# class RigsTextListField(TextListField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# class RigsNumberField(NumberField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# class RigsBooleanField(BooleanField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# class RigsAttachmentsField(AttachmentsField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# class RigsDateField(DateField):
#     def __init__(self, name: RigsKeys):
#         _validate_key(name, RigsKeys)
#         super().__init__(name=name)


# # endregion


# # region Team
# class TeamTextField(TextField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# class TeamTextListField(TextListField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# class TeamNumberField(NumberField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# class TeamBooleanField(BooleanField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# class TeamAttachmentsField(AttachmentsField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# class TeamDateField(DateField):
#     def __init__(self, name: TeamKeys):
#         _validate_key(name, TeamKeys)
#         super().__init__(name=name)


# # endregion


# # region ChemFillup
# class ChemFillupTextField(TextField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# class ChemFillupTextListField(TextListField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# class ChemFillupNumberField(NumberField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# class ChemFillupBooleanField(BooleanField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# class ChemFillupAttachmentsField(AttachmentsField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# class ChemFillupDateField(DateField):
#     def __init__(self, name: ChemFillupKeys):
#         _validate_key(name, ChemFillupKeys)
#         super().__init__(name=name)


# # endregion


# # region ChemRigProducts
# class ChemRigProductsTextField(TextField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# class ChemRigProductsTextListField(TextListField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# class ChemRigProductsNumberField(NumberField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# class ChemRigProductsBooleanField(BooleanField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# class ChemRigProductsAttachmentsField(AttachmentsField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# class ChemRigProductsDateField(DateField):
#     def __init__(self, name: ChemRigProductsKeys):
#         _validate_key(name, ChemRigProductsKeys)
#         super().__init__(name=name)


# # endregion


# # region CrmBasePartitions
# class CrmBasePartitionsTextField(TextField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# class CrmBasePartitionsTextListField(TextListField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# class CrmBasePartitionsNumberField(NumberField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# class CrmBasePartitionsBooleanField(BooleanField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# class CrmBasePartitionsAttachmentsField(AttachmentsField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# class CrmBasePartitionsDateField(DateField):
#     def __init__(self, name: CrmBasePartitionsKeys):
#         _validate_key(name, CrmBasePartitionsKeys)
#         super().__init__(name=name)


# # endregion


# # region OldInspections
# class OldInspectionsTextField(TextField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# class OldInspectionsTextListField(TextListField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# class OldInspectionsNumberField(NumberField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# class OldInspectionsBooleanField(BooleanField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# class OldInspectionsAttachmentsField(AttachmentsField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# class OldInspectionsDateField(DateField):
#     def __init__(self, name: OldInspectionsKeys):
#         _validate_key(name, OldInspectionsKeys)
#         super().__init__(name=name)


# # endregion


# # region EditForms
# class EditFormsTextField(TextField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# class EditFormsTextListField(TextListField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# class EditFormsNumberField(NumberField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# class EditFormsBooleanField(BooleanField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# class EditFormsAttachmentsField(AttachmentsField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# class EditFormsDateField(DateField):
#     def __init__(self, name: EditFormsKeys):
#         _validate_key(name, EditFormsKeys)
#         super().__init__(name=name)


# # endregion


# # region Fines
# class FinesTextField(TextField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# class FinesTextListField(TextListField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# class FinesNumberField(NumberField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# class FinesBooleanField(BooleanField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# class FinesAttachmentsField(AttachmentsField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# class FinesDateField(DateField):
#     def __init__(self, name: FinesKeys):
#         _validate_key(name, FinesKeys)
#         super().__init__(name=name)


# # endregion


# # region OldEndOfShiftIssueReport
# class OldEndOfShiftIssueReportTextField(TextField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# class OldEndOfShiftIssueReportTextListField(TextListField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# class OldEndOfShiftIssueReportNumberField(NumberField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# class OldEndOfShiftIssueReportBooleanField(BooleanField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# class OldEndOfShiftIssueReportAttachmentsField(AttachmentsField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# class OldEndOfShiftIssueReportDateField(DateField):
#     def __init__(self, name: OldEndOfShiftIssueReportKeys):
#         _validate_key(name, OldEndOfShiftIssueReportKeys)
#         super().__init__(name=name)


# # endregion


# # region BonusPeriods
# class BonusPeriodsTextField(TextField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# class BonusPeriodsTextListField(TextListField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# class BonusPeriodsNumberField(NumberField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# class BonusPeriodsBooleanField(BooleanField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# class BonusPeriodsAttachmentsField(AttachmentsField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# class BonusPeriodsDateField(DateField):
#     def __init__(self, name: BonusPeriodsKeys):
#         _validate_key(name, BonusPeriodsKeys)
#         super().__init__(name=name)


# # endregion


# # region BonusesFines
# class BonusesFinesTextField(TextField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# class BonusesFinesTextListField(TextListField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# class BonusesFinesNumberField(NumberField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# class BonusesFinesBooleanField(BooleanField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# class BonusesFinesAttachmentsField(AttachmentsField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# class BonusesFinesDateField(DateField):
#     def __init__(self, name: BonusesFinesKeys):
#         _validate_key(name, BonusesFinesKeys)
#         super().__init__(name=name)


# # endregion


# # region OldIssues
# class OldIssuesTextField(TextField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# class OldIssuesTextListField(TextListField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# class OldIssuesNumberField(NumberField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# class OldIssuesBooleanField(BooleanField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# class OldIssuesAttachmentsField(AttachmentsField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# class OldIssuesDateField(DateField):
#     def __init__(self, name: OldIssuesKeys):
#         _validate_key(name, OldIssuesKeys)
#         super().__init__(name=name)


# # endregion


# # region Sources
# class SourcesTextField(TextField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# class SourcesTextListField(TextListField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# class SourcesNumberField(NumberField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# class SourcesBooleanField(BooleanField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# class SourcesAttachmentsField(AttachmentsField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# class SourcesDateField(DateField):
#     def __init__(self, name: SourcesKeys):
#         _validate_key(name, SourcesKeys)
#         super().__init__(name=name)


# # endregion


# # region CustomerSteps
# class CustomerStepsTextField(TextField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# class CustomerStepsTextListField(TextListField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# class CustomerStepsNumberField(NumberField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# class CustomerStepsBooleanField(BooleanField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# class CustomerStepsAttachmentsField(AttachmentsField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# class CustomerStepsDateField(DateField):
#     def __init__(self, name: CustomerStepsKeys):
#         _validate_key(name, CustomerStepsKeys)
#         super().__init__(name=name)


# # endregion


# # region BarcodeTypes
# class BarcodeTypesTextField(TextField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# class BarcodeTypesTextListField(TextListField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# class BarcodeTypesNumberField(NumberField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# class BarcodeTypesBooleanField(BooleanField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# class BarcodeTypesAttachmentsField(AttachmentsField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# class BarcodeTypesDateField(DateField):
#     def __init__(self, name: BarcodeTypesKeys):
#         _validate_key(name, BarcodeTypesKeys)
#         super().__init__(name=name)


# # endregion
